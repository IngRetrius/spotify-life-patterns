"""
Tests for transformation.label_activities.

The heuristic rules take a single pd.Series (one session) and return a
(label, confidence) tuple. We feed them the canonical scenarios from
the transformation ADR plus edge cases that exercise the duration
gates and the `aislado` fallback.
"""

import pandas as pd
import pytest

from transformation.label_activities import (
    classify_session,
    rule_aislado,
    rule_ducha,
    rule_gimnasio,
    rule_tareas,
    MIN_CONFIDENCE,
)


def _session(duration_minutes: float, hour_of_day: int, n_skips: int,
             day_of_week: int = 2, n_tracks: int = 10) -> pd.Series:
    """Build a single session row with the fields the rules read."""
    return pd.Series({
        "duration_minutes": duration_minutes,
        "hour_of_day":      hour_of_day,
        "n_skips":          n_skips,
        "day_of_week":      day_of_week,
        "n_tracks":         n_tracks,
    })


class TestCanonicalScenarios:
    """
    The four sessions documented in docs/decisions/transformation_layer.md.
    These are the real production sessions and their expected labels.
    """

    def test_late_night_long_session_is_tasks_with_full_confidence(self):
        # 103 min at 3am with 0 skips -> tareas (1.0)
        label, score = classify_session(_session(103.5, 3, 0))
        assert label == "tareas"
        assert score == pytest.approx(1.0, abs=0.01)

    def test_short_afternoon_session_is_shower(self):
        # 14 min at 17h with 0 skips -> ducha (0.8)
        # 17h is NOT in SHOWER_HOURS (6-10, 20-23), so no hour bonus.
        # Gate passes (5 <= 14.5 <= 20) -> 0.5 + 0.3 (0 skips) = 0.8
        label, score = classify_session(_session(14.5, 17, 0))
        assert label == "ducha"
        assert score == pytest.approx(0.8, abs=0.01)

    def test_evening_long_session_is_gym(self):
        # 62 min at 20h with 2 skips -> gimnasio (1.0)
        label, score = classify_session(_session(62.3, 20, 2))
        assert label == "gimnasio"
        assert score == pytest.approx(1.0, abs=0.01)

    def test_very_short_session_is_aislado_not_mislabeled(self):
        # 2.6 min at 23h with 0 skips.
        # Before the duration-gate fix this was mislabeled as "ducha"
        # because the hour and zero-skips bonuses still summed to 0.5
        # despite the short duration failing the shower band. Now the
        # gate blocks that path and rule_aislado picks it up as what it
        # really is: brief exploratory listening, not a routine.
        label, score = classify_session(_session(2.6, 23, 0))
        assert label == "aislado"
        assert score >= MIN_CONFIDENCE
        assert score == pytest.approx(0.5, abs=0.01)


class TestDurationGate:
    """
    Gate semantics: routine rules return 0 outside their duration band,
    regardless of how strong the secondary signals look.
    """

    def test_shower_returns_zero_below_band(self):
        # 2 minutes is below the shower band (5-20). Even with the
        # strongest hour and skip signals, rule_ducha must return 0.
        assert rule_ducha(_session(2.0, 8, 0)) == 0.0

    def test_shower_returns_zero_above_band(self):
        # 25 minutes is above the shower band.
        assert rule_ducha(_session(25.0, 8, 0)) == 0.0

    def test_gym_returns_zero_below_band(self):
        # 30 minutes is below the gym band (35-110).
        assert rule_gimnasio(_session(30.0, 18, 0)) == 0.0

    def test_gym_returns_zero_above_band(self):
        # 120 minutes is above the gym band.
        assert rule_gimnasio(_session(120.0, 18, 0)) == 0.0

    def test_tasks_returns_zero_below_band(self):
        # 30 minutes is below the tasks band (40-300).
        assert rule_tareas(_session(30.0, 3, 0)) == 0.0

    def test_tasks_upper_cap_filters_overnight_playback(self):
        # 6-hour session is above the tasks cap (300 min). This guards
        # against accidental all-night playback being labeled as study.
        assert rule_tareas(_session(360.0, 3, 0)) == 0.0


class TestAislado:
    """
    Casual listening rule: short OR very few tracks, not a routine.
    """

    def test_fires_on_short_duration(self):
        # 3 min, 10 tracks, 0 skips -> gate via duration < 5.
        assert rule_aislado(_session(3.0, 14, 0, n_tracks=10)) == 0.5

    def test_fires_on_few_tracks_even_if_longer(self):
        # 8 min, 2 tracks -> gate via n_tracks <= 2.
        assert rule_aislado(_session(8.0, 14, 0, n_tracks=2)) == 0.5

    def test_does_not_fire_on_normal_session(self):
        # 14 min, 10 tracks -> neither short nor track-thin. Gate fails.
        assert rule_aislado(_session(14.0, 14, 0, n_tracks=10)) == 0.0

    def test_skip_adds_bonus(self):
        # Any skip signals exploratory listening.
        assert rule_aislado(_session(3.0, 14, 1)) == pytest.approx(0.7, abs=0.01)

    def test_max_confidence_is_below_routine_max(self):
        # aislado caps at 0.7. A legitimate shower (up to 1.0) should
        # win when both gates open.
        aislado_max = rule_aislado(_session(4.0, 8, 3, n_tracks=2))
        assert aislado_max <= 0.7


class TestTieBreakingAndRouting:
    """
    Verifies that routine rules outrank aislado when both are plausible,
    and that genuine non-matches fall back to 'desconocido'.
    """

    def test_routine_beats_aislado_on_border_session(self):
        # 5 min at 8am, 0 skips, 2 tracks.
        #   - ducha: gate passes (5 in band), 0.5 + 0.3 + 0.2 = 1.0
        #   - aislado: gate passes (n_tracks <= 2), 0.5
        # Ducha must win.
        label, _ = classify_session(_session(5.0, 8, 0, n_tracks=2))
        assert label == "ducha"

    def test_mid_duration_mid_afternoon_falls_back_to_unknown(self):
        # 25 min at 2pm, 3 skips, 10 tracks.
        # Fails every routine gate (25 not in 5-20, 35-110, 40-300).
        # Fails aislado gate (25 >= 5 and n_tracks > 2).
        # -> desconocido.
        label, _ = classify_session(_session(25.0, 14, 3, n_tracks=10))
        assert label == "desconocido"
