"""
Tests for transformation.build_sessions.

We exercise the pure helpers (assign_sessions, build_session_records)
directly with hand-built DataFrames. No database involved.
"""

import pandas as pd
import pytest

from transformation.build_sessions import (
    SESSION_GAP_MINUTES,
    assign_sessions,
    build_session_records,
    make_session_id,
)


def _plays(rows):
    """Build a plays DataFrame from (played_at_iso, duration_ms) tuples."""
    df = pd.DataFrame(rows, columns=["played_at", "duration_ms"])
    df["played_at"] = pd.to_datetime(df["played_at"], utc=True)
    df["track_id"] = [f"t{i}" for i in range(len(df))]
    df["artist_id"] = ["a0"] * len(df)
    return df


class TestAssignSessions:
    def test_plays_within_small_gap_form_single_session(self):
        # Three tracks each 4 minutes apart -> all well under the 30-min threshold
        plays = _plays([
            ("2025-04-01T10:00:00Z", 180_000),
            ("2025-04-01T10:04:00Z", 180_000),
            ("2025-04-01T10:08:00Z", 180_000),
        ])

        result = assign_sessions(plays)

        assert result["session_num"].nunique() == 1, (
            "Plays with gaps well under SESSION_GAP_MINUTES should form one session"
        )

    def test_plays_with_large_gap_split_into_two_sessions(self):
        # Two tracks close together, then a 45-minute gap, then two more.
        # 45 min > 30 min threshold -> must split.
        plays = _plays([
            ("2025-04-01T10:00:00Z", 180_000),
            ("2025-04-01T10:05:00Z", 180_000),
            ("2025-04-01T10:50:00Z", 180_000),   # gap = 45 min from previous
            ("2025-04-01T10:55:00Z", 180_000),
        ])

        result = assign_sessions(plays)

        # First two plays share a session_num; last two share a different one
        session_nums = result.sort_values("played_at")["session_num"].tolist()
        assert session_nums[0] == session_nums[1], "First two plays must be in the same session"
        assert session_nums[2] == session_nums[3], "Last two plays must be in the same session"
        assert session_nums[1] != session_nums[2], (
            "A 45-minute gap must start a new session"
        )

    def test_threshold_sanity(self):
        # Guards against accidental constant changes. If this fails, the
        # gap-boundary assumptions in the other tests also need revisiting.
        assert SESSION_GAP_MINUTES == 30

    def test_three_sessions_from_two_large_gaps(self):
        plays = _plays([
            ("2025-04-01T08:00:00Z", 120_000),
            ("2025-04-01T09:00:00Z", 120_000),   # 60 min gap -> new session
            ("2025-04-01T10:30:00Z", 120_000),   # 90 min gap -> new session
        ])

        result = assign_sessions(plays)
        assert result["session_num"].nunique() == 3


class TestBuildSessionRecords:
    def test_end_time_includes_last_track_duration(self):
        # Single session; last track starts at 10:05 and lasts 3 min -> end 10:08
        plays = _plays([
            ("2025-04-01T10:00:00Z", 180_000),
            ("2025-04-01T10:05:00Z", 180_000),
        ])

        assigned = assign_sessions(plays)
        records = build_session_records(assigned)

        assert len(records) == 1
        r = records[0]
        assert r["start_time"].startswith("2025-04-01T10:00:00")
        assert r["end_time"].startswith("2025-04-01T10:08:00")
        assert r["duration_minutes"] == pytest.approx(8.0, abs=0.01)
        assert r["n_tracks"] == 2

    def test_session_id_is_deterministic(self):
        start = pd.Timestamp("2025-04-01T10:00:00Z")
        assert make_session_id(start) == make_session_id(start)


class TestBuildSessionRecordsTz:
    """Regression tests for the America/Bogota (UTC-5) timezone fix.

    hour_of_day and day_of_week must reflect local Bogota time, not UTC.
    See .planning/phases/01-timezone-fix/01-CONTEXT.md for background.
    """

    def test_hour_of_day_uses_bogota_time_not_utc(self):
        # 05:00 UTC == 00:00 Bogota (UTC-5). hour_of_day must be 0, not 5.
        plays = _plays([("2025-04-01T05:00:00Z", 180_000)])
        assigned = assign_sessions(plays)
        records = build_session_records(assigned)

        assert records[0]["hour_of_day"] == 0, (
            "05:00 UTC must map to midnight Bogota (hour 0), not 5"
        )

    def test_day_of_week_uses_bogota_time_not_utc(self):
        # Monday 03:00 UTC == Sunday 22:00 Bogota.
        # day_of_week must be 6 (Sun), not 0 (Mon).
        plays = _plays([("2025-04-07T03:00:00Z", 180_000)])
        assigned = assign_sessions(plays)
        records = build_session_records(assigned)

        assert records[0]["day_of_week"] == 6, (
            "Monday 03:00 UTC must map to Sunday in Bogota (day_of_week=6), not 0"
        )

    def test_hour_of_day_mid_afternoon(self):
        # 20:00 UTC == 15:00 Bogota. Regression guard on non-midnight-crossing cases.
        plays = _plays([("2025-04-01T20:00:00Z", 180_000)])
        assigned = assign_sessions(plays)
        records = build_session_records(assigned)

        assert records[0]["hour_of_day"] == 15, (
            "20:00 UTC must map to 15:00 Bogota, not 20"
        )
