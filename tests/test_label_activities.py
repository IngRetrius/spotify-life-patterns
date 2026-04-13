"""
Tests for transformation.label_activities.

The heuristic rules take a single pd.Series (one session) and return a
(label, confidence) tuple. We feed them the exact scenarios listed in
the transformation ADR, which are also the 4 real sessions seen in
production so far.
"""

import pandas as pd
import pytest

from transformation.label_activities import classify_session, MIN_CONFIDENCE


def _session(duration_minutes: float, hour_of_day: int, n_skips: int,
             day_of_week: int = 2, n_tracks: int = 10) -> pd.Series:
    """Build a single session row with the fields rules care about."""
    return pd.Series({
        "duration_minutes": duration_minutes,
        "hour_of_day":      hour_of_day,
        "n_skips":          n_skips,
        "day_of_week":      day_of_week,
        "n_tracks":         n_tracks,
    })


class TestClassifySession:
    # Each case is sourced from docs/decisions/transformation_layer.md
    # and represents a real labeled session from production.

    def test_late_night_long_session_is_tasks_with_full_confidence(self):
        # 103 min at 3am with 0 skips -> tasks (1.0)
        label, score = classify_session(_session(103.5, 3, 0))
        assert label == "tareas"
        assert score == pytest.approx(1.0, abs=0.01)

    def test_short_afternoon_session_is_shower(self):
        # 14 min at 17h with 0 skips -> shower (0.8)
        # Note: 17h is NOT in SHOWER_HOURS (6-10, 20-23), so no hour bonus.
        # duration in 5-20 (+0.5) + n_skips == 0 (+0.3) = 0.8
        label, score = classify_session(_session(14.5, 17, 0))
        assert label == "ducha"
        assert score == pytest.approx(0.8, abs=0.01)

    def test_evening_hour_long_session_is_gym(self):
        # 62 min at 20h with 2 skips -> gym (1.0)
        label, score = classify_session(_session(62.3, 20, 2))
        assert label == "gimnasio"
        assert score == pytest.approx(1.0, abs=0.01)

    def test_very_short_night_session_is_shower_above_threshold(self):
        # 2.6 min at 23h with 0 skips -> shower with score >= MIN_CONFIDENCE.
        # rule_ducha: duration not in 5-20 (0) + n_skips == 0 (0.3) + 23 in SHOWER (0.2) = 0.5
        # rule_tareas: duration not > 40 (0) + n_skips <= 5 (0.2) + 23 in NIGHT_STUDY (0.3) = 0.5
        # Ties go to "ducha" because RULES dict iterates ducha -> gimnasio -> tareas.
        label, score = classify_session(_session(2.6, 23, 0))
        assert label == "ducha"
        assert score >= MIN_CONFIDENCE
        assert score == pytest.approx(0.5, abs=0.01)

    def test_no_rule_triggers_falls_back_to_unknown(self):
        # A 3-minute mid-afternoon session with many skips matches nothing
        # meaningful. Verifies the MIN_CONFIDENCE fallback path.
        label, _ = classify_session(_session(3.0, 14, 20))
        assert label == "desconocido"
