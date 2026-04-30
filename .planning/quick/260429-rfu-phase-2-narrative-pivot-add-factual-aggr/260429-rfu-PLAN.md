---
phase: quick-260429-rfu
plan: 01
type: execute
wave: 1
depends_on: [260429-lyn]
files_modified:
  - dashboard/queries.py
  - dashboard/app.py
autonomous: true
requirements:
  - PIVOT2-01-plays-by-month
  - PIVOT2-02-top-artists
  - PIVOT2-03-diversity-by-month
  - PIVOT2-04-dow-hour-heatmap
  - PIVOT2-05-listening-patterns-reorg

must_haves:
  truths:
    - "queries.py exports four new functions: load_plays_by_month, load_top_artists, load_diversity_by_month, load_dow_hour_heatmap"
    - "All four queries convert played_at to America/Bogota BEFORE extracting month/dow/hour"
    - "load_dow_hour_heatmap normalizes day-of-week so Monday=0, Sunday=6 (matches Python convention used elsewhere in app.py)"
    - "load_dow_hour_heatmap fills missing (dow, hour) combinations with zeros for a continuous 7x24 grid"
    - "app.py imports the four new functions, has cached accessors with @st.cache_data(ttl=timedelta(hours=3))"
    - "Listening Patterns section has 4 rows: Plays by Month (full width) -> Top Tracks + Top Artists (2 col) -> Plays by Hour + Diversity by Month (2 col) -> DoW x Hour heatmap (full width)"
    - "All st.dataframe / st.plotly_chart calls use use_container_width=True (NOT width='stretch') because streamlit==1.40.2 in requirements.txt"
    - "Country map block, warning banner, Sessions/Activity-by-Hour, Day Detail untouched"
  artifacts:
    - path: "dashboard/queries.py"
      provides: "Four new aggregation queries against raw_plays"
    - path: "dashboard/app.py"
      provides: "Reorganized Listening Patterns section with four new charts in fact zone"
---

# Phase 2 Plan — Add factual aggregates to Zone 1

## Objective

Build out the "facts" zone of the dashboard with four data-derived charts that tell honest stories about listening behavior — without any heuristic inference. Counterweight to the inference critique (Phase 3+) so the dashboard has substance beyond the case study.

## Tasks

### Task 1: Add 4 queries to dashboard/queries.py

**Append after `load_activity_by_hour` (end of file).**

1. `load_plays_by_month(engine) -> pd.DataFrame`
   - SQL: `SELECT DATE_TRUNC('month', played_at AT TIME ZONE 'America/Bogota')::date AS month, COUNT(*) AS plays, ROUND(SUM(duration_ms) / 60000.0, 1) AS minutes FROM raw_plays GROUP BY month ORDER BY month ASC`
   - Empty-DataFrame safe.

2. `load_top_artists(engine, limit=10) -> pd.DataFrame`
   - SQL: `SELECT artist_name, COUNT(*) AS play_count FROM raw_plays GROUP BY artist_name ORDER BY play_count DESC LIMIT {limit}`
   - Mirror of `load_top_tracks`.

3. `load_diversity_by_month(engine) -> pd.DataFrame`
   - SQL: `SELECT DATE_TRUNC('month', played_at AT TIME ZONE 'America/Bogota')::date AS month, COUNT(DISTINCT track_name || '||' || artist_name) AS unique_tracks, COUNT(DISTINCT artist_name) AS unique_artists FROM raw_plays GROUP BY month ORDER BY month ASC`
   - The `'||'` literal separator avoids collisions when track and artist names share substrings.

4. `load_dow_hour_heatmap(engine) -> pd.DataFrame`
   - SQL: extract dow + hour from `played_at AT TIME ZONE 'America/Bogota'`. Normalize dow so Monday=0 (Postgres returns Sunday=0): `((EXTRACT(DOW FROM ...)::int + 6) % 7) AS dow`.
   - Post-query: ensure all 7×24 = 168 combinations exist by left-joining a Cartesian grid with `fillna(0)`. Convert plays to int.

### Task 2: Wire app.py

- Update the import block to add the 4 new functions.
- Add 4 cached accessors next to the existing ones (`_plays_by_month`, `_top_artists`, `_diversity_by_month`, `_dow_hour_heatmap`), all `@st.cache_data(ttl=timedelta(hours=3))`.
- Add `DOW_LABELS_MON0 = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]` constant.
- Replace the existing `Listening Patterns` section body (currently 2 cols: plays-by-hour + top-tracks) with a 4-row layout:
  - Row 1 (full width): **Plays by Month** — `px.bar` with green Spotify color, hover shows plays + minutes.
  - Row 2 (2 cols): **Top Tracks** (left, existing) | **Top Artists** (right, new) — orange `#E8754C`.
  - Row 3 (2 cols): **Plays by Hour** (left, existing) | **Diversity by Month** (right, new line chart with two series).
  - Row 4 (full width): **Day of Week × Hour** heatmap using `go.Heatmap` with green `Greens` colorscale, Y axis labeled with `DOW_LABELS_MON0`.

### Task 3: Static verification + commit

- `python -c "import ast; ast.parse(open('dashboard/queries.py').read()); ast.parse(open('dashboard/app.py').read())"`
- Atomic commits: one for queries.py (`feat(quick-260429-rfu-01): add 4 factual aggregate queries`), one for app.py (`feat(quick-260429-rfu-02): wire 4 new charts in Listening Patterns`).

## Success criteria

- Both files parse cleanly.
- `dashboard/queries.py` exports 4 new functions.
- `dashboard/app.py` shows 4 new charts in the Listening Patterns section.
- Country map, warning banner, Sessions, Activity by Hour, Day Detail all unchanged.
- No `width="stretch"` anywhere (Cloud-pinned Streamlit 1.40.2 doesn't support it for `st.dataframe`).
- No Unicode emojis in any Python `print()` (none added; only HTML in markdown if needed).

## Out of scope (Phase 3+)

- New vs repeat tracks per month
- "The Rules" panel (label_activities.py code render)
- Confidence histogram
- Sensitivity analysis
- Adversarial example picker
- Lineage diagram
- Modifications to existing queries
