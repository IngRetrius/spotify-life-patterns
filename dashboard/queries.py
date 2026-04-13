"""
Consultas SQL para el dashboard.

Separamos las queries de la UI para que:
- sea facil cambiar la fuente de datos sin tocar el layout
- cada funcion tenga una responsabilidad clara
- se puedan testear las queries de forma aislada

Todas las funciones reciben un SQLAlchemy engine y retornan DataFrames.
Usamos SQLAlchemy (no psycopg2 crudo) porque pandas.read_sql lo requiere.
"""

import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
import os

load_dotenv()


# ── Conexion ──────────────────────────────────────────────────────────────────

def _get_password() -> str:
    """
    Lee SUPABASE_DB_PASSWORD desde dos fuentes segun el ambiente:

    - Local: cargado por python-dotenv desde el archivo .env
    - Streamlit Cloud: disponible en st.secrets (no es una env var automatica)

    Si ninguna fuente tiene el valor, lanza un error claro en vez de
    intentar conectarse con una URL invalida.
    """
    password = os.getenv("SUPABASE_DB_PASSWORD")
    if not password:
        try:
            import streamlit as st
            password = st.secrets.get("SUPABASE_DB_PASSWORD")
        except Exception:
            pass
    if not password:
        raise EnvironmentError(
            "SUPABASE_DB_PASSWORD not found. "
            "Set it in .env (local) or Streamlit Cloud secrets (deploy)."
        )
    return password


def get_engine():
    """
    Crea un SQLAlchemy engine apuntando al pooler de Supabase.

    Por que SQLAlchemy y no psycopg2 directo:
    - pandas.read_sql espera un engine o una URL de conexion
    - psycopg2 crudo genera UserWarning en pandas >= 2.0
    - SQLAlchemy permite reutilizar la conexion con st.cache_resource
    """
    password = _get_password()
    url = (
        f"postgresql+psycopg2://postgres.ofjjslcrzzllzaiiygya:{password}"
        f"@aws-1-us-east-1.pooler.supabase.com:6543/postgres"
        f"?sslmode=require"
    )
    return create_engine(url)


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
            "WHERE activity_label != 'desconocido' "
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
    df["activity_label"] = df["activity_label"].fillna("sin etiquetar")
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
