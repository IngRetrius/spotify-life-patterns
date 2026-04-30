"""
Parametrized labeling for the Sensitivity Analysis panel.

WARNING - duplication notice
----------------------------
This module is a parametrized port of the rules in
``transformation/label_activities.py``. It exists for one reason: the
Sensitivity panel needs to re-classify sessions under shifted thresholds
without mutating module-level globals on the canonical labeler.

If the canonical rules change, this file MUST be updated to match.

The dashboard runs a drift check on every page load: it re-classifies
the live sessions with the *original* thresholds and compares against
the labels stored in the DB. If they don't match, the panel surfaces a
warning so the inconsistency is impossible to miss.

API
---
``reclassify(df, **thresholds) -> pd.Series`` returns one label per row.
"""

from __future__ import annotations

import pandas as pd

# -- Canonical thresholds (mirror of label_activities.py) --------------------

SHOWER_HOURS_DEFAULT      = set(range(6, 11))  | set(range(20, 24))
GYM_HOURS_DEFAULT         = set(range(5, 11))  | set(range(16, 23))
NIGHT_STUDY_HOURS_DEFAULT = set(range(22, 24)) | set(range(0, 6))

SHOWER_DURATION_DEFAULT  = (5, 20)
GYM_DURATION_DEFAULT     = (35, 110)
TASKS_DURATION_DEFAULT   = (40, 300)

CASUAL_MAX_MINUTES_DEFAULT = 5
CASUAL_MAX_TRACKS_DEFAULT  = 2
MIN_CONFIDENCE_DEFAULT     = 0.4


# -- Rule helpers (parametrized) ---------------------------------------------

def _rule_shower(row, hours: set, duration: tuple[int, int]) -> float:
    lo, hi = duration
    if not (lo <= row["duration_minutes"] <= hi):
        return 0.0
    score = 0.5
    if row["n_skips"] == 0:           score += 0.3
    if row["hour_of_day"] in hours:   score += 0.2
    return score


def _rule_gym(row, hours: set, duration: tuple[int, int]) -> float:
    lo, hi = duration
    if not (lo <= row["duration_minutes"] <= hi):
        return 0.0
    score = 0.4
    if row["n_skips"] <= 2:           score += 0.3
    if row["hour_of_day"] in hours:   score += 0.3
    return score


def _rule_tasks(row, hours: set, duration: tuple[int, int]) -> float:
    lo, hi = duration
    if not (lo <= row["duration_minutes"] <= hi):
        return 0.0
    score = 0.5
    if row["n_skips"] <= 5:           score += 0.2
    if row["hour_of_day"] in hours:   score += 0.3
    return score


def _rule_casual(row, max_minutes: int, max_tracks: int) -> float:
    if not (row["duration_minutes"] < max_minutes
            or row["n_tracks"] <= max_tracks):
        return 0.0
    score = 0.5
    if row["n_skips"] >= 1:           score += 0.2
    return score


# -- Public API --------------------------------------------------------------

def reclassify(
    df: pd.DataFrame,
    *,
    shower_hours: set[int] | None = None,
    gym_hours: set[int] | None = None,
    night_study_hours: set[int] | None = None,
    shower_duration: tuple[int, int] = SHOWER_DURATION_DEFAULT,
    gym_duration: tuple[int, int] = GYM_DURATION_DEFAULT,
    tasks_duration: tuple[int, int] = TASKS_DURATION_DEFAULT,
    casual_max_minutes: int = CASUAL_MAX_MINUTES_DEFAULT,
    casual_max_tracks: int = CASUAL_MAX_TRACKS_DEFAULT,
    min_confidence: float = MIN_CONFIDENCE_DEFAULT,
) -> pd.Series:
    """
    Apply the rules to ``df`` with the supplied thresholds and return
    one label per row.

    ``df`` must contain the columns: duration_minutes, n_tracks, n_skips,
    hour_of_day. Rows are processed independently — there is no
    cross-row state.
    """
    if shower_hours is None:
        shower_hours = SHOWER_HOURS_DEFAULT
    if gym_hours is None:
        gym_hours = GYM_HOURS_DEFAULT
    if night_study_hours is None:
        night_study_hours = NIGHT_STUDY_HOURS_DEFAULT

    labels: list[str] = []
    for _, row in df.iterrows():
        scores = {
            "shower": _rule_shower(row, shower_hours, shower_duration),
            "gym":    _rule_gym(row, gym_hours, gym_duration),
            "tasks":  _rule_tasks(row, night_study_hours, tasks_duration),
            "casual": _rule_casual(row, casual_max_minutes, casual_max_tracks),
        }
        best_label = max(scores, key=scores.get)
        best_score = round(scores[best_label], 2)
        labels.append(best_label if best_score >= min_confidence else "unknown")

    return pd.Series(labels, index=df.index, name="recomputed_label")


def shifted_hour_set(base: set[int], shift: int) -> set[int]:
    """
    Shift every hour in ``base`` by ``shift`` positions, wrapping at 24.

    Used by the sensitivity panel: a slider in [-3, +3] becomes a
    ``shifted_hour_set(GYM_HOURS_DEFAULT, slider_value)`` call.
    """
    return {(h + shift) % 24 for h in base}
