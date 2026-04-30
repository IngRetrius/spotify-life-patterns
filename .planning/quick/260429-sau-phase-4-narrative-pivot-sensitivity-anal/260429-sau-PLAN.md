---
phase: quick-260429-sau
plan: 01
type: execute
wave: 1
depends_on: [260429-lyn, 260429-rfu, 260429-rmq]
files_modified:
  - dashboard/queries.py
  - dashboard/sensitivity.py
  - dashboard/app.py
autonomous: true
requirements:
  - PIVOT4-01-sensitivity-module
  - PIVOT4-02-sensitivity-query
  - PIVOT4-03-sensitivity-panel
  - PIVOT4-04-lineage-diagram
  - PIVOT4-05-assumptions-list

must_haves:
  truths:
    - "dashboard/sensitivity.py exists with a parametrized port of label_activities.py rules"
    - "dashboard/sensitivity.py top docstring explicitly acknowledges that it duplicates the canonical rules and must be updated when those change"
    - "queries.py exports load_sessions_for_sensitivity that returns ALL sessions joined with features (no pagination)"
    - "app.py shows a Sensitivity Analysis section between Adversarial Examples and Day Detail with side-by-side label-count comparison under shifted thresholds"
    - "app.py shows a Methodology section at the bottom with a graphviz lineage diagram and an explicit assumptions list"
    - "All chart calls use use_container_width=True (1.40.2 pin)"
    - "Country map, warning banner, residual KPI, rules panel, confidence histogram, adversarial picker, Day Detail unchanged"
  artifacts:
    - path: "dashboard/sensitivity.py"
      provides: "Parametrized labeler used solely for the sensitivity panel"
    - path: "dashboard/queries.py"
      provides: "Unpaginated sessions-with-features loader"
    - path: "dashboard/app.py"
      provides: "Sensitivity panel + Methodology section closing the case study"
---

# Phase 4 Plan — Close the case study (sensitivity + methodology)

## Objective

Land the two final components of the narrative pivot:

1. **Sensitivity analysis** — visually demonstrates that the labels are a function of arbitrary thresholds. Shift `gym_hours` by 1 hour, watch 30% of "gym" labels disappear. Single most powerful technical proof of the case-study thesis.
2. **Methodology section** — a `graphviz` lineage diagram + explicit assumptions list at the bottom of the dashboard. Closing argument: here are the bricks every chart was built on.

After Phase 4 the dashboard has a complete narrative arc: facts → warning → critique → proof of fragility → methodology.

## Components

### 1. dashboard/sensitivity.py — parametrized labeler

A new module that ports the labeling rules from `transformation/label_activities.py` with all thresholds as function parameters. Top-of-file docstring explicitly says:

> WARNING: This file duplicates the canonical labeling rules from
> `transformation/label_activities.py`. It exists for the sensitivity
> panel only — to re-classify sessions under shifted thresholds without
> mutating module-level globals on the canonical labeler. If the rules
> change in `label_activities.py`, update this file too.

Public API:

```python
def reclassify(
    df: pd.DataFrame,
    *,
    shower_hours: set[int],
    gym_hours: set[int],
    night_study_hours: set[int],
    shower_duration: tuple[int, int] = (5, 20),
    gym_duration: tuple[int, int] = (35, 110),
    tasks_duration: tuple[int, int] = (40, 300),
    casual_max_minutes: int = 5,
    casual_max_tracks: int = 2,
    min_confidence: float = 0.4,
) -> pd.Series:
    """Return per-row activity_label given the supplied thresholds."""
```

Sanity check the port reproduces the canonical labels when called with the original constants — the dashboard surfaces a warning if the baseline doesn't match the live labels (drift detector).

### 2. queries.py — load_sessions_for_sensitivity

```python
def load_sessions_for_sensitivity(engine) -> pd.DataFrame:
    """All sessions joined with features. Used only by the sensitivity panel."""
```

Returns columns: `session_id`, `duration_minutes`, `n_tracks`, `hour_of_day`, `day_of_week`, `n_skips`, `live_label` (the current canonical label for the drift check).

### 3. app.py — Sensitivity Analysis panel

Placed between `Adversarial Examples` and `Day Detail` in the inference zone.

UI:
- Three sliders: "Shift shower hours by ±", "Shift gym hours by ±", "Shift night-study hours by ±". Each is a small range like `[-3, +3]`.
- Side-by-side bar chart: baseline label counts vs. shifted label counts, colored by activity.
- A summary metric: "X% of labels changed under these thresholds."
- A short caption explaining the mechanics: "These are the rules from the panel above with the hour windows shifted by the slider amounts. Every other threshold is held fixed."

Computation runs in pandas — no DB roundtrip on slider change. The sessions DataFrame is cached.

### 4. app.py — Methodology section

Placed at the very bottom of the layout, just above the footer. Two parts:

- **Lineage diagram** via `st.graphviz_chart` showing:
  ```
  Spotify API
      ↓
  raw_plays  (UTC timestamps, conn_country, duration_ms)
      ↓
  sessions   (30-min gap rule applied — arbitrary)
      ↓
  session_features  (n_skips computed)
      ↓
  activity_labels   (5 hand-coded rules — heuristic, not measurement)
  ```
  Each arrow annotated with what gets added or assumed at that step.

- **Assumptions list** in markdown, ~6 bullets:
  - Session boundary = 30 min gap (not 20, not 45 — arbitrary)
  - All inferences assume Bogota timezone matches the user's actual location
  - No audio features available (Spotify restricted endpoints in 2024)
  - Skip detection uses a 50% completion threshold (arbitrary)
  - Activity labels assume the user behaves consistently over time
  - Country = `conn_country` from Spotify, can include VPN noise

## Layout (post-Phase 4)

```
Header
Overview KPIs
Listening Patterns (4-row Phase 2 layout)
Global Footprint
================ Warning banner ================
Residual KPI
The Rules expander
Sessions
Confidence Distribution
Activity by Hour
Adversarial Examples
Sensitivity Analysis        ← NEW (Phase 4 #1)
Day Detail
================ Methodology ================
Lineage diagram             ← NEW (Phase 4 #2a)
Assumptions list            ← NEW (Phase 4 #2b)
Footer
```

## Constraints

- Three files modified; one is new (`dashboard/sensitivity.py`).
- No `width='stretch'` regressions.
- No literal `%` in new SQL.
- No Unicode in Python `print()` (none added; only HTML/markdown if rendered).
- No Claude attribution in commits.
- `transformation/label_activities.py` is read-only.
- Country map, banner, all Phase 1-3 components untouched.

## Out of scope

- Standalone "About / methodology" multipage app
- Re-running the canonical labeler from the dashboard
- Threshold-sensitivity for skip detection or session boundary (only hour windows are exposed)
- Persisting alternate-threshold labels to the DB
