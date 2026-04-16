"""
SQL queries for the dashboard.

Keeping queries out of the UI so we can:
- swap the data source without touching the layout
- give each function a single responsibility
- test queries in isolation

Every function takes a SQLAlchemy engine and returns a DataFrame.
We use SQLAlchemy (not raw psycopg2) because pandas.read_sql expects it.
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
    Top-level metrics shown in the header KPI cards.

    Returns a dict with:
    - total_plays      : number of plays recorded
    - total_minutes    : total minutes listened
    - total_sessions   : sessions detected
    - top_activity     : most frequent label (excluding 'unknown')
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

    top_activity = activity_row[0] if activity_row else "no data"

    return {
        "total_plays":    int(plays_row[0]),
        "total_minutes":  float(plays_row[1]) if plays_row[1] else 0.0,
        "total_sessions": int(sessions_row[0]),
        "top_activity":   top_activity,
    }


def load_sessions(engine) -> pd.DataFrame:
    """
    Sessions joined with their features and activity labels.

    LEFT JOIN so sessions without a label (if any) still show up with
    activity_label = NULL, replaced downstream with 'unlabeled'.
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
    """Top tracks by play count."""
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
    Plays distribution by hour of day.

    Converts to Bogota local time (UTC-5) so the patterns reflect
    the user's actual behavior.
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
    # Fill missing hours with 0 so the bar chart is continuous
    all_hours = pd.DataFrame({"hour": range(24)})
    df = all_hours.merge(df, on="hour", how="left").fillna(0)
    df["plays"] = df["plays"].astype(int)
    return df


def load_activity_counts(engine) -> pd.DataFrame:
    """Session count per activity, for the bar chart."""
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


def load_plays_by_country(engine) -> pd.DataFrame:
    """
    Plays y minutos escuchados por pais de conexion (ISO alpha-2).

    Excluye filas sin pais (registros de API sin conn_country, y los
    reproducidos con VPN/ZZ que ya se almacenaron como NULL).
    """
    query = """
        SELECT
            conn_country                                        AS country_code,
            COUNT(*)                                            AS plays,
            ROUND(SUM(duration_ms) / 60000.0, 1)               AS minutes_played
        FROM raw_plays
        WHERE conn_country IS NOT NULL
        GROUP BY conn_country
        ORDER BY plays DESC
    """
    return pd.read_sql(query, engine)


def load_activity_by_hour(engine) -> pd.DataFrame:
    """
    Session count per hour of day, broken down by activity label.

    Joins sessions (which store hour_of_day) with activity_labels so we
    can see which activities cluster at which times of day.  The result
    is used for a stacked bar chart in the Listening Patterns section.
    """
    query = """
        SELECT
            s.hour_of_day AS hour,
            al.activity_label,
            COUNT(*) AS sessions
        FROM sessions s
        JOIN activity_labels al ON s.session_id = al.session_id
        GROUP BY s.hour_of_day, al.activity_label
        ORDER BY s.hour_of_day, al.activity_label
    """
    df = pd.read_sql(query, engine)
    if df.empty:
        return df

    # Ensure every hour (0-23) x every activity combination is present
    # so gaps render as 0-height bars, keeping the x-axis continuous.
    activities = df["activity_label"].unique().tolist()
    grid = (
        pd.DataFrame({"hour": range(24)})
        .assign(key=1)
        .merge(pd.DataFrame({"activity_label": activities, "key": 1}), on="key")
        .drop(columns="key")
    )
    df = grid.merge(df, on=["hour", "activity_label"], how="left").fillna(0)
    df["sessions"] = df["sessions"].astype(int)
    return df
