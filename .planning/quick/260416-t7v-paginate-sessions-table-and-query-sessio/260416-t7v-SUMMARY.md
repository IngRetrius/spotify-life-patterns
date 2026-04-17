---
phase: 260416-t7v
plan: 01
subsystem: dashboard
tags: [pagination, performance, streamlit, sql]
requires:
  - dashboard/queries.py::load_sessions (existing)
  - sessions / session_features / activity_labels tables
provides:
  - dashboard/queries.py::load_sessions(engine, limit=50, offset=0)
  - dashboard/queries.py::count_sessions(engine)
  - dashboard/queries.py::load_sessions_for_day(engine, day)
  - dashboard/app.py::_sessions_page / _sessions_count / _sessions_for_day cached wrappers
affects:
  - dashboard Sessions detail table (now paginated server-side)
  - dashboard Day Detail block (now day-scoped SQL instead of pandas filter)
tech-stack:
  patterns:
    - server-side LIMIT/OFFSET pagination keyed by a st.number_input control
    - day-scoped SQL read (AT TIME ZONE 'America/Bogota')::date = :day
key-files:
  modified:
    - dashboard/queries.py
    - dashboard/app.py
decisions:
  - Keep page size at 50 to match the plan contract and the existing dashboard visual budget.
  - Cache _sessions_page by (page, page_size) and _sessions_for_day by day so page switching and day picking each reuse cached slices for the 3h TTL.
metrics:
  duration: ~4 min
  completed: 2026-04-16
  tasks_completed: 2
  tasks_total: 3  # Task 3 is human-verify, handled by orchestrator
---

# Phase 260416-t7v Plan 01: Paginate Sessions Table and Query Sessions by Day Summary

Paginate the dashboard's Sessions detail table server-side and swap the Day Detail pandas filter for a dedicated SQL query, cutting per-page payload and eliminating the full `sessions` scan that used to happen on every cache miss.

## What changed

### `dashboard/queries.py`

- `load_sessions(engine, limit=50, offset=0) -> pd.DataFrame`
  - Same SELECT/JOIN/ORDER BY as before; appended `LIMIT :limit OFFSET :offset`.
  - Switched from a bare string query to `sqlalchemy.text(...)` with `params={"limit", "offset"}`.
  - Kept the `fillna` post-processing for `n_skips` and `activity_label` so downstream shape is identical.
- `count_sessions(engine) -> int` (new)
  - Simple `SELECT COUNT(*) FROM sessions` used to compute the total page count.
- `load_sessions_for_day(engine, day) -> pd.DataFrame` (new)
  - Same columns as `load_sessions`, filtered by `(s.start_time AT TIME ZONE 'America/Bogota')::date = :day`, ordered DESC, no LIMIT.
  - Same fillna normalization so `format_sessions_table` works unchanged.

### `dashboard/app.py`

- Imports now include `count_sessions` and `load_sessions_for_day`.
- Removed the old `_sessions()` cached wrapper. Added:
  - `SESSIONS_PAGE_SIZE = 50`
  - `_sessions_page(page, page_size)` — cached slice loader.
  - `_sessions_count()` — cached total row count.
  - `_sessions_for_day(day)` — cached day-scoped loader.
  - All three use `@st.cache_data(ttl=timedelta(hours=3))`, matching the rest of the wrappers.
- Sessions table block (`col_table`) now:
  - Reads total via `_sessions_count()`; computes `total_pages = ceil(total / 50)`.
  - Renders a `st.number_input("Page", 1..total_pages)` above the table.
  - Calls `_sessions_page(int(page), SESSIONS_PAGE_SIZE)` and renders the slice via `format_sessions_table`.
  - Adds a caption: `Page N of M — X total sessions`.
- Day Detail block (`col_summary`) now computes `day_sessions = _sessions_for_day(selected_day)`; removed the three lines that fetched all sessions, added a `date` column in pandas, and filtered in memory.

## Verification

- `from dashboard.queries import load_sessions, count_sessions, load_sessions_for_day` imports cleanly; `load_sessions` signature exposes `limit=50, offset=0` (confirmed by `inspect.signature`).
- `python -c "import ast; ast.parse(open('dashboard/app.py').read())"` parses without error.
- Static check confirms `_sessions_page`, `_sessions_count`, `_sessions_for_day` exist and the old bare `_sessions()` wrapper is gone; `load_sessions_for_day` and `count_sessions` are referenced in `app.py`.
- No other query in `queries.py` was modified. No other dashboard section (KPIs, activity chart, hour chart, tracks table, activity-by-hour, global footprint) was touched.

## Deviations from Plan

### Verify script caveat

The Task 2 `<automated>` verify snippet uses:
```python
assert '_sessions(' not in src.replace('_sessions_','')
```
That check triggers a false positive because the cleaned source still contains `load_sessions(` and `count_sessions(` (their tail is literally `_sessions(`). The stale wrapper is genuinely gone — verified with a stricter regex (`(?<![a-zA-Z0-9_])_sessions\(\)`) that returned no matches, and via AST function-name scan confirming no `_sessions` function is defined. No code change was needed; the assertion was updated only in the local verification step, not in the source.

Otherwise, the plan was executed as written.

## Commits

- `69e5065` — feat(260416-t7v-01): paginate load_sessions and add count_sessions + load_sessions_for_day
- `490d5c3` — feat(260416-t7v-02): paginate Sessions table and scope Day Detail via SQL

## Known Stubs

None — all three new loaders are wired to real SQL and real cached callers in `app.py`.

## Follow-ups

- Task 3 (human-verify checkpoint) is intentionally skipped; the orchestrator will run the Streamlit dashboard with the user and confirm pagination + Day Detail visually.

## Self-Check: PASSED

- FOUND: `dashboard/queries.py` — `load_sessions(limit=50, offset=0)`, `count_sessions`, `load_sessions_for_day` all importable.
- FOUND: `dashboard/app.py` — `_sessions_page`, `_sessions_count`, `_sessions_for_day` defined; old `_sessions()` wrapper removed; `SESSIONS_PAGE_SIZE = 50`; `st.number_input("Page", ...)` and `Page N of M` caption present; Day Detail uses `_sessions_for_day(selected_day)`.
- FOUND commit `69e5065` in worktree `git log`.
- FOUND commit `490d5c3` in worktree `git log`.
