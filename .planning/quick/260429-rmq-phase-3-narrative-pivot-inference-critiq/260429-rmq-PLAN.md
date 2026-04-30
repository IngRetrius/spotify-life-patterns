---
phase: quick-260429-rmq
plan: 01
type: execute
wave: 1
depends_on: [260429-lyn, 260429-rfu]
files_modified:
  - dashboard/queries.py
  - dashboard/app.py
autonomous: true
requirements:
  - PIVOT3-01-residual-kpi
  - PIVOT3-02-rules-panel
  - PIVOT3-03-confidence-histogram
  - PIVOT3-04-adversarial-picker

must_haves:
  truths:
    - "Inference zone (everything between the warning banner and Day Detail) shows a residual KPI prominent at the top"
    - "A collapsible 'The Rules' panel renders the actual source of label_activities.py via st.code"
    - "A confidence-score histogram is rendered with explicit copy that it is NOT a probability"
    - "An adversarial picker lets the user pick an activity label and view 3 random sessions with their tracks"
    - "Three new queries exist: load_confidence_distribution, load_random_sessions_by_label, load_session_tracks"
    - "All new SQL uses MOD() not literal % (DBAPI placeholder collision lesson from quick-260429-rfu hotfix)"
    - "Streamlit pin still respected: use_container_width=True everywhere; no width='stretch'"
    - "Country map, warning banner, Listening Patterns charts, Day Detail all unchanged"
  artifacts:
    - path: "dashboard/queries.py"
      provides: "Three new queries powering the critique narrative"
    - path: "dashboard/app.py"
      provides: "Critique zone components placed under the warning banner"
---

# Phase 3 Plan — Build the inference critique zone

## Objective

Turn the inference zone (everything below the amber warning banner) from a chart gallery into an honest case study. Four components, each chosen because it makes a specific weakness of the labeling visible to the reader without requiring them to read code.

## Components

### 1. Residual KPI — "What I cannot tell you"

A prominent metric placed immediately under the warning banner showing what % of sessions fell into `casual` or `unknown`. Computed in pandas from the existing `_activity_counts()` accessor — no new query.

Format: large green metric + supporting caption. If 50%+ of sessions are residual, that *is* the most honest result of the project and must be visible.

### 2. "The Rules" panel

A `st.expander("Show the labeling rules — see exactly what 'gym' means")` that reveals the actual source of `transformation/label_activities.py` via `st.code(language="python")`. Read the file at module level so the panel always reflects shipped code, not a copy that drifts.

Slice from the constants section (`# -- Hour windows`) through the `RULES = {...}` dict — that's the meaningful part. Skip imports, the `run()` orchestration, and database SQL.

When the reader sees `if 6 <= hour <= 10 and 5 <= duration <= 20: score += 0.5`, the magic dies. This is the highest-impact component of the phase.

### 3. Confidence-score histogram

New query `load_confidence_distribution(engine)` returns the raw `confidence_score` from `activity_labels`. Render with `px.histogram` using ~10 bins. Pair with explicit copy: *"This is NOT a 0.65 = 65% probability. It is the sum of how many rules fired. A score of 0.65 means roughly 3 of 5 conditions matched — not 'I'm 65% sure.'"*

### 4. Adversarial example picker

A `st.selectbox` of activity labels (from existing `_activity_counts()` data) + a button "Show 3 random sessions" that pulls 3 random sessions of that label and lists their tracks.

Two new queries:
- `load_random_sessions_by_label(engine, label, n=3)` — `ORDER BY RANDOM() LIMIT n`
- `load_session_tracks(engine, session_id)` — joins `raw_plays` to a session via the session's `[start_time, start_time + duration_minutes]` time window

Time-window join syntax: `WHERE played_at >= s.start_time AND played_at < s.start_time + (s.duration_minutes * INTERVAL '1 minute')`.

Why this wins narratively: one shower session containing a podcast, or one gym session containing ballads, kills credibility faster than ten paragraphs of disclaimers.

## Layout (post-Phase 3)

```
Header
KPI grid
Listening Patterns (Phase 2 layout)
Global Footprint
================ Warning banner ================
Residual KPI                   <- NEW (Phase 3 #1)
The Rules panel (collapsed)    <- NEW (Phase 3 #2)
Sessions (existing)
Confidence histogram           <- NEW (Phase 3 #3)
Activity by Hour (existing)
Adversarial picker             <- NEW (Phase 3 #4)
Day Detail (existing)
Footer
```

## Files

### `dashboard/queries.py`

Append three queries:

```python
def load_confidence_distribution(engine) -> pd.DataFrame: ...
def load_random_sessions_by_label(engine, label: str, n: int = 3) -> pd.DataFrame: ...
def load_session_tracks(engine, session_id: str) -> pd.DataFrame: ...
```

Use `text()` with named params for the two parameterized ones. No `%` literals anywhere.

### `dashboard/app.py`

- Import the 3 new queries.
- Add 1 cached accessor for `_confidence_distribution()`. The two adversarial queries are NOT cached (random + per-session) — call directly.
- Add a module-level helper `_load_rules_source()` that reads `transformation/label_activities.py` once and returns the rules block as a string.
- Add 4 visual sections in the layout slots above.

## Constraints

- Only `dashboard/queries.py` and `dashboard/app.py` modified.
- No `width='stretch'` (1.40.2 pin).
- No literal `%` in new SQL — use `MOD()` if needed.
- No Unicode in Python `print()` (none added).
- No Claude attribution in commits.
- `transformation/label_activities.py` is read-only — only displayed, never modified.
- All new SQL uses `text()` for parameterized queries.
- Country map, warning banner, Listening Patterns, Day Detail, header, footer all untouched.

## Out of scope (Phase 4)

- Sensitivity analysis (re-label engine with shifted thresholds, compare counts)
- Lineage diagram + assumptions list (markdown / graphviz)
- "Why I built this" / about page
