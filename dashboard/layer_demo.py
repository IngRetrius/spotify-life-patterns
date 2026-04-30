"""
Didactic SQL strings for the dashboard's "Layer Architecture" section.

This module holds two SQL strings used purely for comparison in the dashboard:

  - BAD_SQL:  Reconstructs sessions from `raw_plays` using window functions on
              every page load (anti-pattern: business logic inside the
              dashboard query).
  - GOOD_SQL: Reads from the silver-layer `sessions` table that the pipeline
              has already built (pattern: business logic inside
              `transformation/build_sessions.py`).

Important: these strings are NEVER executed. The dashboard renders them as
code via `st.code(...)` only. They exist to make the medallion-layer trade-off
visible to a reader.
"""

__all__ = ["BAD_SQL", "GOOD_SQL"]


BAD_SQL = """\
-- Anti-pattern: rebuild sessions from raw_plays on every dashboard load.
-- Same business rule (30-min gap) re-implemented here in SQL instead of
-- reusing the silver `sessions` table.
WITH ordered AS (
    SELECT
        played_at,
        track_id,
        duration_ms
    FROM raw_plays
    ORDER BY played_at
),
gapped AS (
    SELECT
        played_at,
        track_id,
        duration_ms,
        LAG(played_at) OVER (ORDER BY played_at) AS prev_played_at,
        EXTRACT(
            EPOCH FROM (
                played_at - LAG(played_at) OVER (ORDER BY played_at)
            )
        ) / 60 AS gap_minutes
    FROM ordered
),
flagged AS (
    SELECT
        played_at,
        track_id,
        duration_ms,
        gap_minutes,
        -- matches SESSION_GAP_MINUTES in transformation/build_sessions.py
        (gap_minutes IS NULL OR gap_minutes > 30)::int AS is_new_session
    FROM gapped
),
numbered AS (
    SELECT
        played_at,
        track_id,
        duration_ms,
        SUM(is_new_session) OVER (ORDER BY played_at) AS session_num
    FROM flagged
),
aggregated AS (
    SELECT
        session_num,
        MIN(played_at) AS start_time,
        MAX(played_at) AS end_time,
        COUNT(*)       AS n_tracks,
        SUM(duration_ms) / 60000.0 AS duration_minutes
    FROM numbered
    GROUP BY session_num
)
SELECT
    start_time,
    end_time,
    duration_minutes,
    n_tracks,
    -- timezone logic duplicated here AND in every other dashboard query
    EXTRACT(HOUR FROM start_time AT TIME ZONE 'UTC' AT TIME ZONE 'America/Bogota') AS hour_of_day,
    EXTRACT(DOW  FROM start_time AT TIME ZONE 'UTC' AT TIME ZONE 'America/Bogota') AS day_of_week
FROM aggregated
ORDER BY start_time DESC
LIMIT 50;
"""


GOOD_SQL = """\
-- All session/timezone logic lives in transformation/build_sessions.py
SELECT session_id, start_time, end_time, duration_minutes,
       n_tracks, hour_of_day, day_of_week
FROM sessions
ORDER BY start_time DESC
LIMIT 50;
"""
