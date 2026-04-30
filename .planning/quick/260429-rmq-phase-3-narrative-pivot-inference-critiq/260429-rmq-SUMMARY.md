---
phase: quick-260429-rmq
status: complete
date: 2026-04-30
commits:
  - debd18a
  - fffa574
files_modified:
  - dashboard/queries.py
  - dashboard/app.py
---

# Quick Task 260429-rmq — Summary

**Description:** Phase 3 narrative pivot — build the inference critique zone

## Requirements addressed

| ID | Requirement | Result |
|----|-------------|--------|
| PIVOT3-01 | Residual KPI | Done — 3-column metric strip immediately under the warning banner |
| PIVOT3-02 | Rules panel | Done — `st.expander` rendering `transformation/label_activities.py` source via `st.code` |
| PIVOT3-03 | Confidence histogram | Done — `px.histogram` with explanatory copy beside it |
| PIVOT3-04 | Adversarial picker | Done — selectbox + button + tracks-per-session table |

## Layout shipped (inference zone)

```
================ Warning banner (existing) ================
Residual KPI strip                              ← NEW
The Rules expander                              ← NEW (collapsed by default)
Sessions section (existing — activity bar + table)
Confidence Distribution histogram               ← NEW
Activity by Hour (existing)
Adversarial Examples picker                     ← NEW
Day Detail (existing)
```

## Architecture decisions

- **Residual computed in-memory.** Reused the existing `_activity_counts()` accessor instead of adding `load_label_summary()`. The category set is small (5–6 rows) and the math (sum, share) is trivial; a new SQL query would have been ceremony.
- **Rules panel reads source dynamically.** `_rules_source()` opens `transformation/label_activities.py` and slices from the `Hour windows` block through the `RULES` dict. Cached as `@st.cache_resource(show_spinner=False)` since the file changes only on deploy. If we hardcoded the rules as a string, it would silently drift away from what the labeling engine actually does — exactly the kind of dishonesty this phase is trying to call out.
- **Adversarial picker has a session-state seed.** Without it, every Streamlit rerun (e.g. typing in another widget) would reshuffle the random sample. The seed only advances when the user clicks "Roll 3 random sessions", so the displayed examples stay stable until the user wants new ones.
- **Time-window join for session tracks.** Sessions don't store a per-track FK. `load_session_tracks(session_id)` joins `raw_plays` on `[start_time, start_time + duration_minutes)` so the picker can show what actually played without any schema migration. Boundary chosen as `<` (not `<=`) so a track that started exactly at the next session's start is not double-counted.
- **Confidence colors warning-orange (`#f5a623`).** Same hue as the warning banner border to visually link the histogram to the case-study narrative — "this lives in the inference zone, treat it accordingly."

## Constraints honored

- Two files modified: `dashboard/queries.py` (+62 lines), `dashboard/app.py` (+223 lines).
- No `width="stretch"` regressions — pinned Streamlit 1.40.2 still happy.
- No literal `%` in new SQL (Phase 2 lesson honored).
- All parameterized queries use SQLAlchemy `text()` with named bindings.
- No Unicode in Python `print()` (none added).
- No Claude attribution in commits.
- `transformation/label_activities.py` is read-only — only displayed, never modified.
- Country map, warning banner, Phase 2 charts, Day Detail all untouched.

## Verification

Static (`python -c`):
- `app.py` and `queries.py` parse cleanly.
- All 3 new accessors / helpers (`_confidence_distribution`, `_rules_source`, `_adv_sessions`) defined.
- All 4 narrative anchors present: residual KPI title, expander label, "Confidence Distribution", "Adversarial Examples", "Roll 3 random sessions" button.
- Country map and warning banner intact.
- No `width='stretch'` anywhere.

Runtime: pending Streamlit Cloud rebuild + manual smoke test (live Supabase queries).

## Files

- `dashboard/queries.py` — appended `load_confidence_distribution`, `load_random_sessions_by_label`, `load_session_tracks`.
- `dashboard/app.py` — added imports, `_confidence_distribution()` accessor, `_rules_source()` helper, residual KPI strip, Rules expander, Confidence Distribution section, Adversarial Examples section.

## Out of scope (Phase 4)

- **Sensitivity analysis** — re-run labeling with shifted thresholds (e.g. `gym_hours ± 1h`) and compare counts side-by-side. Requires a Python module that imports the labeling functions and calls them with monkey-patched constants.
- **Lineage diagram** — `raw plays → sessions (30-min gap rule) → activities (5 hand-coded rules)` as a graphviz / mermaid block plus an explicit assumptions list.
- **About / methodology page** — promote the case-study framing to its own narrative page rather than scattering it across captions.
