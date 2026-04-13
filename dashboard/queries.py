"""
Consultas SQL para el dashboard.

Separamos las queries de la UI para que:
- sea facil cambiar la fuente de datos sin tocar el layout
- cada funcion tenga una responsabilidad clara
- se puedan testear las queries de forma aislada

Todas las funciones reciben un SQLAlchemy engine y retornan DataFrames.
Usamos SQLAlchemy (no psycopg2 crudo) porque pandas.read_sql lo requiere.
"""

import os
import sys

import pandas as pd
from sqlalchemy import text
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.connection import get_engine  # re-exported for backward compat

load_dotenv()


# ── Queries ───────────────────────────────────────────────────────────────────

def load_kpis(engine) -> dict:
    """
    Metricas de alto nivel para las tarjetas del header.

    Retorna un dict con:
    - total_plays      : numero de reproducciones registradas
    - total_minutes    : minutos totales escuchados
    - total_sessions   : sesiones detectadas
    - top_activity     : actividad mas frecuente entre las etiquetadas
    """
    with engine.connect() as conn:
        plays_row = conn.execute(text(
            "SELECT COUNT(*) AS total_plays, "
            "ROUND(SUM(duration_ms) / 60000.0, 1) AS total_minutes "
            "FROM raw_plays"
        )).fetchone()

        sessions_row = conn.execute(text(
            "SELECT COUNT(*) AS total_sessions FROM sessions"
        )).fetchone()

        activity_row = conn.execute(text(
            "SELECT activity_label, COUNT(*) AS cnt "
            "FROM activity_labels "
            "WHERE activity_label != 'unknown' "
            "GROUP BY activity_label "
            "ORDER BY cnt DESC LIMIT 1"
        )).fetchone()

    top_activity = activity_row[0] if activity_row else "sin datos"

    return {
        "total_plays":    int(plays_row[0]),
        "total_minutes":  float(plays_row[1]) if plays_row[1] else 0.0,
        "total_sessions": int(sessions_row[0]),
        "top_activity":   top_activity,
    }


def load_sessions(engine) -> pd.DataFrame:
    """
    Sesiones con sus features y etiquetas de actividad.

    Hace un LEFT JOIN para que sesiones sin etiqueta (si las hay)
    aparezcan igual con activity_label = NULL.
    """
    query = """
        SELECT
            s.session_id,
            s.start_time AT TIME ZONE 'America/Bogota' AS start_time,
            s.duration_minutes,
            s.n_tracks,
            s.hour_of_day,
            s.day_of_week,
            sf.n_skips,
            al.activity_label,
            al.confidence_score
        FROM sessions s
        LEFT JOIN session_features sf ON s.session_id = sf.session_id
        LEFT JOIN activity_labels  al ON s.session_id = al.session_id
        ORDER BY s.start_time DESC
    """
    df = pd.read_sql(query, engine)
    df["n_skips"] = df["n_skips"].fillna(0).astype(int)
    df["activity_label"] = df["activity_label"].fillna("unlabeled")
    return df


def load_top_tracks(engine, limit: int = 10) -> pd.DataFrame:
    """Top tracks por numero de reproducciones."""
    query = f"""
        SELECT
            track_name,
            artist_name,
            COUNT(*) AS play_count
        FROM raw_plays
        GROUP BY track_name, artist_name
        ORDER BY play_count DESC
        LIMIT {limit}
    """
    return pd.read_sql(query, engine)


def load_plays_by_hour(engine) -> pd.DataFrame:
    """
    Distribucion de reproducciones por hora del dia.

    Convierte a hora de Colombia (UTC-5) para que los patrones
    reflejen el comportamiento real del usuario.
    """
    query = """
        SELECT
            EXTRACT(HOUR FROM played_at AT TIME ZONE 'America/Bogota')::int AS hour,
            COUNT(*) AS plays
        FROM raw_plays
        GROUP BY hour
        ORDER BY hour
    """
    df = pd.read_sql(query, engine)
    # Rellenar horas sin plays con 0 para que el grafico sea continuo
    all_hours = pd.DataFrame({"hour": range(24)})
    df = all_hours.merge(df, on="hour", how="left").fillna(0)
    df["plays"] = df["plays"].astype(int)
    return df


def load_activity_counts(engine) -> pd.DataFrame:
    """Conteo de sesiones por actividad para el grafico de barras."""
    query = """
        SELECT
            activity_label,
            COUNT(*) AS sessions,
            ROUND(AVG(confidence_score)::numeric, 2) AS avg_confidence
        FROM activity_labels
        GROUP BY activity_label
        ORDER BY sessions DESC
    """
    return pd.read_sql(query, engine)


def load_plays_for_day(engine, day) -> pd.DataFrame:
    """
    Plays that happened on a given calendar day (America/Bogota).

    The date filter is applied after the timezone conversion so a play
    that happened at 01:00 Bogota on Apr 13 shows up on Apr 13 — even
    though its UTC timestamp would already be April 14 in some cases.
    """
    query = """
        SELECT
            (played_at AT TIME ZONE 'America/Bogota') AS played_at_local,
            track_name,
            artist_name,
            ROUND(duration_ms / 60000.0, 2) AS duration_minutes
        FROM raw_plays
        WHERE (played_at AT TIME ZONE 'America/Bogota')::date = :day
        ORDER BY played_at_local ASC
    """
    return pd.read_sql(text(query), engine, params={"day": day})


def load_available_dates(engine) -> pd.DataFrame:
    """
    Distinct calendar days (Bogota) that contain at least one play.

    Used by the date picker to set min/max bounds and highlight days
    that actually have data.
    """
    query = """
        SELECT DISTINCT
            (played_at AT TIME ZONE 'America/Bogota')::date AS day
        FROM raw_plays
        ORDER BY day DESC
    """
    return pd.read_sql(query, engine)
