---
phase: quick-260429-sau
status: complete
date: 2026-04-30
commits:
  - 5ab6cbc
  - 22c9b8c
files_modified:
  - dashboard/queries.py
  - dashboard/app.py
files_created:
  - dashboard/sensitivity.py
---

# Quick Task 260429-sau — Summary

**Description:** Phase 4 narrative pivot — sensitivity analysis + methodology section

## Requirements addressed

| ID | Requirement | Result |
|----|-------------|--------|
| PIVOT4-01 | Parametrized labeler (`dashboard/sensitivity.py`) | Done — public `reclassify()` + `shifted_hour_set()` |
| PIVOT4-02 | `load_sessions_for_sensitivity` query | Done — unpaginated join with `live_label` for drift check |
| PIVOT4-03 | Sensitivity panel | Done — 3 sliders + side-by-side bar comparison + "labels changed %" |
| PIVOT4-04 | Lineage diagram | Done — `st.graphviz_chart` color-coded by data confidence |
| PIVOT4-05 | Assumptions list | Done — 6 explicit bullets naming arbitrary choices |

## Final layout

```
Header
Overview KPIs
Listening Patterns (Phase 2)
Global Footprint
================ Warning banner ================
Residual KPI
The Rules expander
Sessions
Confidence Distribution
Activity by Hour
Adversarial Examples
Sensitivity Analysis           <- NEW (Phase 4)
Day Detail
================ Methodology ================ <- NEW (Phase 4)
Lineage diagram
Assumptions list
Footer
```

## Architecture decisions

- **Parametrized port over monkey-patching.** Considered importing `transformation/label_activities.py` and mutating its module-level globals (`SHOWER_HOURS = ...`) to re-classify under different thresholds. Rejected: thread-unsafe in Streamlit, and any uncaught exception would leave the canonical labeler with wrong constants. Instead wrote `dashboard/sensitivity.py` as a parametrized port. The duplication is acknowledged in the top docstring AND verified at runtime with a drift check (see next bullet).
- **Drift check baked in.** Every sensitivity panel render reclassifies sessions with the *original* thresholds and compares against the live `activity_label` from the DB. If the port has drifted from the canonical labeler, a warning surfaces in the panel. Means the duplication can't silently rot.
- **Computation in pandas, not SQL.** Slider drag triggers a Streamlit rerun; doing the relabeling in-process (pandas iterrows over `_sensitivity_sessions()` cached for 3h) is fast and avoids hammering Supabase on every slider movement. With only ~few thousand sessions, the iterrows overhead is negligible.
- **Slider range `[-3, +3]`.** Wide enough to demonstrate fragility, narrow enough that users can't accidentally shift a window into nonsense (a `+12` shift would just mirror the rule onto its complementary hours, which would be confusing without context).
- **Lineage diagram colored by data confidence.** Green = factual ingestion, yellow = derived with arbitrary parameters, red = heuristic inference. Forces the reader to see which boxes deserve trust and which don't, before reading the assumptions list.
- **Methodology at the bottom, not the top.** Placed it at the END of the layout (above the footer) so it reads as a closing argument rather than a disclaimer. By the time the user gets there, they've seen all the charts, the rules panel, the histogram, the adversarial examples, the sensitivity comparison — the methodology is the last word, not the first warning.

## Constraints honored

- Three files modified; one new (`dashboard/sensitivity.py`).
- All chart calls use `use_container_width=True` (1.40.2 pin).
- No literal `%` in new SQL.
- All parameterized queries use SQLAlchemy `text()`.
- No Unicode in Python `print()` (none added).
- No Claude attribution in commits.
- `transformation/label_activities.py` is read-only — only ported with explicit acknowledgement.
- Country map, banner, all Phase 1-3 components untouched.

## Verification

Static (`python -c`):
- All three files parse cleanly.
- Sensitivity imports + accessor present.
- Sensitivity panel anchors: "Sensitivity Analysis", "Shift gym hours", "Labels that changed", "baseline rules vs shifted".
- Methodology anchors: section header, `graphviz_chart`, "Assumptions baked into", "30-min gap", "No audio features".
- No `width='stretch'` regressions.

Drift-check verification: pending Streamlit Cloud rebuild + manual smoke. The check re-runs the parametrized labeler against live data on every page load.

## Out of scope (not planned)

- Standalone "About / methodology" multipage app
- Threshold-sensitivity for the 30-min session gap or 50% skip threshold (only hour windows are exposed)
- Persisting alternate-threshold labels to the DB
- Sensitivity sliders for duration bands or skip-count bonuses
- Sweeps over the full parameter space (UI only exposes single-axis shifts)

## Narrative status — case-study arc complete

The four phases of the narrative pivot are shipped:

| Phase | Theme | Components |
|-------|-------|------------|
| 1 (260429-lyn) | Remove false confidence | Drop Top Activity KPI, Confidence progress bar, footer note; add warning banner |
| 2 (260429-rfu) | Build the facts zone | Plays by month, top artists, diversity, dow×hour heatmap |
| 3 (260429-rmq) | Build the critique zone | Residual KPI, Rules panel, Confidence histogram, Adversarial picker |
| 4 (260429-sau) | Close the case study | Sensitivity analysis, Methodology section |

The dashboard now reads as: facts → warning → critique → proof of fragility → methodology. The transformation case study is the product, the listening data is the substrate.
