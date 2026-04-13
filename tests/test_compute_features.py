"""
Tests for transformation.compute_features.detect_skips.

A track is a "skip" when the user moved on before half of its duration
elapsed — i.e. the next play started before duration_ms * 0.5. Skip
detection only makes sense within a session (we do not compare across
sessions), hence the session_id column.
"""

import pandas as pd
import pytest

from transformation.compute_features import SKIP_THRESHOLD, detect_skips


def _plays(rows):
    """
    Build a plays-with-sessions DataFrame.
    Each row: (session_id, track_id, played_at_iso, duration_ms)
    """
    df = pd.DataFrame(rows, columns=["session_id", "track_id", "played_at", "duration_ms"])
    df["played_at"] = pd.to_datetime(df["played_at"], utc=True)
    return df


class TestDetectSkips:
    def test_threshold_is_fifty_percent(self):
        # Guard against accidental changes to the skip definition.
        assert SKIP_THRESHOLD == 0.5

    def test_track_is_skipped_when_next_starts_before_50_percent(self):
        # Track 1: starts at 10:00, duration 4 minutes (240_000 ms).
        # Half duration = 2 minutes. Next track starts at 10:01 (1 min in) -> skip.
        # Track 2: starts at 10:01, last track in session -> no next, not a skip.
        plays = _plays([
            ("s1", "t1", "2025-04-01T10:00:00Z", 240_000),
            ("s1", "t2", "2025-04-01T10:01:00Z", 180_000),
        ])

        result = detect_skips(plays).sort_values("track_id").reset_index(drop=True)

        assert bool(result.loc[result["track_id"] == "t1", "is_skip"].iloc[0]) is True
        # Last track in the session never counts as a skip (no next_played_at)
        assert bool(result.loc[result["track_id"] == "t2", "is_skip"].iloc[0]) is False

    def test_track_is_not_skipped_when_next_starts_after_50_percent(self):
        # Track 1 duration 4 min (240_000 ms). Next track starts 3 min later
        # (well past the 2-min halfway mark) -> not a skip.
        plays = _plays([
            ("s1", "t1", "2025-04-01T10:00:00Z", 240_000),
            ("s1", "t2", "2025-04-01T10:03:00Z", 180_000),
        ])

        result = detect_skips(plays).sort_values("track_id").reset_index(drop=True)

        assert bool(result.loc[result["track_id"] == "t1", "is_skip"].iloc[0]) is False
        assert bool(result.loc[result["track_id"] == "t2", "is_skip"].iloc[0]) is False

    def test_last_track_of_session_is_never_a_skip(self):
        # Only one track in the session -> next_played_at is NaT -> cannot be a skip.
        plays = _plays([
            ("s1", "t1", "2025-04-01T10:00:00Z", 240_000),
        ])

        result = detect_skips(plays)
        assert bool(result["is_skip"].iloc[0]) is False

    def test_skip_detection_is_per_session(self):
        # Two separate sessions. Track t1 ends its session; t2 starts a new one
        # shortly after. Without the per-session guard, t1 would look skipped.
        plays = _plays([
            ("s1", "t1", "2025-04-01T10:00:00Z", 240_000),   # last of s1
            ("s2", "t2", "2025-04-01T10:01:00Z", 180_000),   # first of s2
        ])

        result = detect_skips(plays).sort_values("track_id").reset_index(drop=True)

        # t1 is the last track of session s1, so it has no "next" within s1 -> not a skip
        assert bool(result.loc[result["track_id"] == "t1", "is_skip"].iloc[0]) is False

    def test_skip_counts_aggregate_correctly(self):
        # One session, three tracks. First is skipped (next at 20% mark);
        # second is not skipped (next at 80% mark); third is last -> not a skip.
        plays = _plays([
            ("s1", "t1", "2025-04-01T10:00:00Z", 300_000),   # 5 min track, next at 1:00 -> skip
            ("s1", "t2", "2025-04-01T10:01:00Z", 300_000),   # 5 min track, next at 10:05 -> 4 min played, not skip
            ("s1", "t3", "2025-04-01T10:05:00Z", 180_000),
        ])

        result = detect_skips(plays)
        assert int(result["is_skip"].sum()) == 1
