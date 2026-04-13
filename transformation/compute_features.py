"""
Calculo de features por sesion.

Para cada sesion en sessions, calcula:
- n_skips: canciones escuchadas menos del 50% de su duracion
- avg_bpm, avg_energy, avg_valence, etc.: promedio de audio features
  (seran NULL mientras el endpoint /audio-features este restringido)
- dominant_genre: genero mas frecuente entre los artistas de la sesion

Los resultados se escriben en session_features.

Por que separamos compute_features de build_sessions:
- Single Responsibility: cada script tiene una sola razon de cambiar
- Si los audio features se recuperan en el futuro, solo cambia este script
- Si cambia la logica de skips, no toca el codigo de sesiones

Uso:
    python transformation/compute_features.py
"""

import sys
import uuid
import pandas as pd
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.connection import get_connection as get_db_connection

load_dotenv()

NAMESPACE        = uuid.NAMESPACE_URL
SKIP_THRESHOLD   = 0.5    # se considera skip si se escucho menos del 50%


# ── Carga de datos ────────────────────────────────────────────────────────────

def load_data(conn) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Carga sessions, plays, audio features y artistas en DataFrames."""

    sessions = pd.read_sql(
        "SELECT session_id, start_time, end_time FROM sessions",
        conn
    )
    sessions["start_time"] = pd.to_datetime(sessions["start_time"], utc=True)
    sessions["end_time"]   = pd.to_datetime(sessions["end_time"],   utc=True)

    plays = pd.read_sql(
        "SELECT track_id, artist_id, duration_ms, played_at FROM raw_plays ORDER BY played_at ASC",
        conn
    )
    plays["played_at"] = pd.to_datetime(plays["played_at"], utc=True)

    audio = pd.read_sql(
        """SELECT track_id, tempo, energy, danceability, valence,
                  acousticness, instrumentalness, loudness
           FROM raw_audio_features""",
        conn
    )

    artists = pd.read_sql(
        "SELECT artist_id, genres FROM raw_artists",
        conn
    )

    return sessions, plays, audio, artists


# ── Asignacion de plays a sesiones ────────────────────────────────────────────

def assign_plays_to_sessions(plays: pd.DataFrame, sessions: pd.DataFrame) -> pd.DataFrame:
    """
    Une cada play con su session_id usando un merge por rango de tiempo.

    Para cada play, busca la sesion donde:
        session.start_time <= play.played_at <= session.end_time

    Usamos merge_asof (merge ordenado por clave) en lugar de un JOIN en SQL
    porque es mas eficiente para datos en memoria.
    """
    plays    = plays.sort_values("played_at").reset_index(drop=True)
    sessions = sessions.sort_values("start_time").reset_index(drop=True)

    # merge_asof: para cada play, encuentra la sesion con start_time <= played_at
    merged = pd.merge_asof(
        plays,
        sessions[["session_id", "start_time", "end_time"]],
        left_on="played_at",
        right_on="start_time",
        direction="backward"
    )

    # Filtra plays que cayeron fuera del end_time de su sesion asignada
    merged = merged[merged["played_at"] <= merged["end_time"]]

    return merged


# ── Deteccion de skips ────────────────────────────────────────────────────────

def detect_skips(plays_with_sessions: pd.DataFrame) -> pd.DataFrame:
    """
    Marca un play como 'skip' si la siguiente cancion empezo antes de que
    se escuchara el 50% de la duracion de la actual.

    Logica:
    - tiempo_escuchado = played_at[i+1] - played_at[i]  (en ms)
    - es_skip = tiempo_escuchado < duration_ms[i] * 0.5

    Solo aplica dentro de la misma sesion (no comparamos entre sesiones).
    """
    df = plays_with_sessions.copy().sort_values("played_at")

    df["next_played_at"] = df.groupby("session_id")["played_at"].shift(-1)
    df["listened_ms"] = (
        df["next_played_at"] - df["played_at"]
    ).dt.total_seconds() * 1000

    df["is_skip"] = (
        df["listened_ms"].notna() &
        (df["duration_ms"].notna()) &
        (df["listened_ms"] < df["duration_ms"] * SKIP_THRESHOLD)
    )

    return df


# ── Calculo de features por sesion ────────────────────────────────────────────

def compute_dominant_genre(group: pd.DataFrame, artists: pd.DataFrame) -> str | None:
    """
    Encuentra el genero mas frecuente entre los artistas de la sesion.
    Retorna None si no hay datos de generos (endpoint /artists restringido).
    """
    artist_ids = group["artist_id"].dropna().unique().tolist()
    if not artist_ids:
        return None

    artist_data = artists[artists["artist_id"].isin(artist_ids)]
    all_genres = []

    for genres in artist_data["genres"].dropna():
        if isinstance(genres, list):
            all_genres.extend(genres)

    if not all_genres:
        return None

    return max(set(all_genres), key=all_genres.count)


def build_feature_records(
    plays_with_skips: pd.DataFrame,
    audio: pd.DataFrame,
    artists: pd.DataFrame,
) -> list[dict]:
    """
    Construye los registros de session_features para cada sesion.
    """
    plays_with_audio = plays_with_skips.merge(audio, on="track_id", how="left")
    records = []

    for session_id, group in plays_with_audio.groupby("session_id"):
        n_skips = int(group["is_skip"].sum())

        # Promedios de audio features (NULL si el endpoint esta restringido)
        def safe_mean(col):
            vals = group[col].dropna()
            return round(float(vals.mean()), 4) if len(vals) > 0 else None

        records.append({
            "session_id":        session_id,
            "avg_bpm":           safe_mean("tempo"),
            "avg_energy":        safe_mean("energy"),
            "avg_valence":       safe_mean("valence"),
            "avg_danceability":  safe_mean("danceability"),
            "avg_acousticness":  safe_mean("acousticness"),
            "avg_loudness":      safe_mean("loudness"),
            "n_skips":           n_skips,
            "dominant_genre":    compute_dominant_genre(group, artists),
        })

    return records


# ── Escritura en base de datos ────────────────────────────────────────────────

UPSERT_FEATURES_SQL = """
    INSERT INTO session_features
        (session_id, avg_bpm, avg_energy, avg_valence, avg_danceability,
         avg_acousticness, avg_loudness, n_skips, dominant_genre)
    VALUES
        (%(session_id)s, %(avg_bpm)s, %(avg_energy)s, %(avg_valence)s,
         %(avg_danceability)s, %(avg_acousticness)s, %(avg_loudness)s,
         %(n_skips)s, %(dominant_genre)s)
    ON CONFLICT (session_id) DO UPDATE SET
        n_skips        = EXCLUDED.n_skips,
        dominant_genre = EXCLUDED.dominant_genre,
        avg_bpm        = EXCLUDED.avg_bpm,
        avg_energy     = EXCLUDED.avg_energy;
"""


def upsert_features(cursor, records: list[dict]) -> None:
    """Upsert de features. Actualiza si la sesion ya existe (los skips pueden cambiar)."""
    if not records:
        return
    psycopg2.extras.execute_batch(cursor, UPSERT_FEATURES_SQL, records, page_size=100)


# ── Orquestacion ──────────────────────────────────────────────────────────────

def run() -> None:
    print("=== Calculo de features por sesion ===")

    conn = get_db_connection()
    conn.autocommit = False
    cursor = conn.cursor()

    try:
        sessions, plays, audio, artists = load_data(conn)

        if sessions.empty:
            print("No hay sesiones. Corre build_sessions.py primero.")
            return

        plays_with_sessions = assign_plays_to_sessions(plays, sessions)
        plays_with_skips    = detect_skips(plays_with_sessions)
        records             = build_feature_records(plays_with_skips, audio, artists)

        upsert_features(cursor, records)
        conn.commit()

        print(f"{len(records)} sesiones procesadas:")
        for r in records:
            genre = r["dominant_genre"] or "sin genero"
            print(f"  {r['session_id'][:8]}... | skips: {r['n_skips']} | genero: {genre}")

        print(f"\nResumen: {len(records)} registros en session_features.")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        sys.exit(1)

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    run()
