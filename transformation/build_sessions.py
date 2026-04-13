"""
Construccion de sesiones desde raw_plays.

Una sesion es un bloque continuo de escucha donde el gap entre
canciones consecutivas es menor a SESSION_GAP_MINUTES (30 min).

Algoritmo:
1. Carga raw_plays ordenado por played_at
2. Calcula el gap entre cada play y el anterior
3. Marca el inicio de nueva sesion cuando gap > 30 min
4. Agrupa en sesiones y calcula sus atributos
5. Hace upsert en la tabla sessions

Por que session_id es determinista (uuid5):
- Si reconstruimos las sesiones, los IDs no cambian
- Las referencias desde session_features y activity_labels siguen siendo validas
- El upsert es seguro: mismos datos = mismo ID = DO NOTHING

Uso:
    python transformation/build_sessions.py
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

SESSION_GAP_MINUTES = 30
NAMESPACE           = uuid.NAMESPACE_URL   # base para uuid5 deterministico


# ── Carga de datos ────────────────────────────────────────────────────────────

def load_plays(conn) -> pd.DataFrame:
    """
    Carga todos los plays de raw_plays ordenados por tiempo.
    played_at viene como string ISO — lo convertimos a datetime con timezone UTC.
    """
    query = """
        SELECT track_id, artist_id, duration_ms, played_at
        FROM raw_plays
        ORDER BY played_at ASC
    """
    df = pd.read_sql(query, conn)
    df["played_at"] = pd.to_datetime(df["played_at"], utc=True)
    return df


# ── Logica de sesiones ────────────────────────────────────────────────────────

def make_session_id(start_time: pd.Timestamp) -> str:
    """
    Genera un UUID deterministico basado en el start_time de la sesion.

    uuid5 toma un namespace y un string y siempre produce el mismo UUID
    para los mismos inputs. Esto hace el upsert idempotente.
    """
    return str(uuid.uuid5(NAMESPACE, start_time.isoformat()))


def assign_sessions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Asigna un numero de sesion a cada play.

    Logica:
    1. Calculamos el gap entre played_at[i] y played_at[i-1]
    2. Si gap > SESSION_GAP_MINUTES, es el inicio de una nueva sesion
    3. cumsum() sobre los flags de 'nuevo inicio' da el numero de sesion
    """
    df = df.copy().sort_values("played_at").reset_index(drop=True)

    # Gap en minutos respecto al play anterior
    df["gap_min"] = (
        df["played_at"] - df["played_at"].shift(1)
    ).dt.total_seconds() / 60

    # True en el primer play de cada sesion (gap > umbral o primer play de todo)
    df["is_new_session"] = df["gap_min"].isna() | (df["gap_min"] > SESSION_GAP_MINUTES)
    df["session_num"]    = df["is_new_session"].cumsum()

    return df


def build_session_records(df: pd.DataFrame) -> list[dict]:
    """
    Construye los registros de sesion a insertar en la tabla sessions.

    end_time = played_at del ultimo track + su duracion
    (el usuario escucho hasta el final de la ultima cancion)
    """
    sessions = []

    for session_num, group in df.groupby("session_num"):
        group      = group.sort_values("played_at")
        start_time = group["played_at"].iloc[0]
        last_play  = group.iloc[-1]

        # El fin de la sesion es cuando termina el ultimo track
        last_duration = last_play["duration_ms"] or 0
        end_time      = last_play["played_at"] + pd.Timedelta(milliseconds=last_duration)

        duration_minutes = (end_time - start_time).total_seconds() / 60

        sessions.append({
            "session_id":       make_session_id(start_time),
            "start_time":       start_time.isoformat(),
            "end_time":         end_time.isoformat(),
            "duration_minutes": round(duration_minutes, 2),
            "n_tracks":         len(group),
            "hour_of_day":      start_time.hour,
            "day_of_week":      start_time.dayofweek,   # 0=lunes, 6=domingo
        })

    return sessions


# ── Escritura en base de datos ────────────────────────────────────────────────

UPSERT_SESSION_SQL = """
    INSERT INTO sessions
        (session_id, start_time, end_time, duration_minutes, n_tracks, hour_of_day, day_of_week)
    VALUES
        (%(session_id)s, %(start_time)s, %(end_time)s, %(duration_minutes)s,
         %(n_tracks)s, %(hour_of_day)s, %(day_of_week)s)
    ON CONFLICT (session_id) DO NOTHING;
"""


def upsert_sessions(cursor, sessions: list[dict]) -> int:
    """Inserta sesiones. Ignora las que ya existen (mismo session_id)."""
    if not sessions:
        return 0
    psycopg2.extras.execute_batch(cursor, UPSERT_SESSION_SQL, sessions, page_size=100)
    return cursor.rowcount


# ── Orquestacion ──────────────────────────────────────────────────────────────

def run() -> dict:
    """
    Construye sesiones desde raw_plays y las inserta en sessions.
    Retorna un dict con estadisticas para el orquestador.
    """
    print("=== Construccion de sesiones ===")

    conn = get_db_connection()
    conn.autocommit = False
    cursor = conn.cursor()

    try:
        df = load_plays(conn)

        if df.empty:
            print("raw_plays esta vacia. Nada que procesar.")
            return {"sessions_built": 0}

        print(f"Plays cargados: {len(df)}")

        df       = assign_sessions(df)
        sessions = build_session_records(df)

        print(f"Sesiones detectadas: {len(sessions)}")

        for s in sessions:
            print(f"  {s['start_time'][:16]} | {s['duration_minutes']:.1f} min | {s['n_tracks']} tracks")

        upsert_sessions(cursor, sessions)
        conn.commit()

        print(f"\nResumen: {len(sessions)} sesiones insertadas en sessions.")
        return {"sessions_built": len(sessions), "df_with_sessions": df}

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        sys.exit(1)

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    run()
