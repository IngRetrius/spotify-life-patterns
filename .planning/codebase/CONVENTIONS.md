# Coding Conventions

**Analysis Date:** 2026-04-15

## Naming Patterns

**Files:**
- Snake_case for all Python files: `ingest_plays.py`, `build_sessions.py`, `compute_features.py`
- Dashboard components: `app.py` (UI), `queries.py` (data layer)
- Test files match source: `test_build_sessions.py` for `transformation/build_sessions.py`

**Functions:**
- Snake_case for all function names: `assign_sessions()`, `detect_skips()`, `compute_dominant_genre()`
- Private helpers prefixed with underscore: `_plays()`, `_resolve_password()`, `_format_markdown_table()`
- Public entry points: `run()`, `load_plays()`, `get_connection()`, `get_engine()`

**Variables:**
- Snake_case throughout: `total_plays`, `duration_minutes`, `session_num`, `is_new_session`
- Constants in UPPER_CASE: `SESSION_GAP_MINUTES = 30`, `SKIP_THRESHOLD = 0.5`, `POOLER_HOST`
- Boolean variables often prefixed with `is_` or `has_`: `is_skip`, `is_new_session`, `autocommit`

**Types:**
- Type hints used in function signatures: `def load_plays(conn) -> pd.DataFrame:`, `def run() -> dict:`
- Union syntax: `str | None` (Python 3.10+ style)
- Import DataFrame types: `pd.DataFrame`, `pd.Series`, `pd.Timestamp`

## Code Style

**Formatting:**
- No explicit formatter configured (no .prettierrc or black config found)
- Follows PEP 8 standard indentation (4 spaces)
- Line length appears around 88-100 characters based on existing code
- Docstrings in triple-quoted format (see below)

**Linting:**
- No explicit linter configuration found (no .eslintrc or pylintrc)
- Code follows PEP 8 conventions
- Imports organized with standard library first, then third-party

## Import Organization

**Order (observed in source files):**
1. Standard library imports: `sys`, `os`, `time`, `argparse`, `uuid`
2. Third-party libraries: `pandas`, `psycopg2`, `spotipy`, `streamlit`, `plotly`
3. Local imports: from `.db.connection`, from `.transformation.*`, from `.ingestion.*`

**Path Aliases:**
- No path aliases configured
- Full relative imports used: `from db.connection import get_connection`
- sys.path manipulation in entry points: `sys.path.insert(0, os.path.dirname(...))`

## Error Handling

**Patterns:**
- Try/except/finally for database operations:
  ```python
  try:
      df = load_plays(conn)
      # process...
      cursor.execute(...)
      conn.commit()
  except Exception as e:
      conn.rollback()
      print(f"\nERROR: {e}")
      sys.exit(1)
  finally:
      cursor.close()
      conn.close()
  ```

- Explicit error propagation with sys.exit(1) in scripts: `scripts/run_pipeline.py`, ingestion modules
- Rate limit handling in Spotify client with retry logic:
  ```python
  for attempt in range(MAX_RETRY_ATTEMPTS):
      try:
          return sp.current_user_recently_played(**params)
      except SpotifyException as e:
          if e.http_status == 429:
              wait = int(e.headers.get("Retry-After", ...))
              time.sleep(wait)
  ```

- Environment variable fallback chain: `db/connection.py` checks env vars, then st.secrets, then raises

## Logging

**Framework:** Built-in `print()` statements (no structured logging library)

**Patterns:**
- Print progress markers: `print("=== Construccion de sesiones ===")` 
- Print step results: `print(f"Plays cargados: {len(df)}")`
- Print row-level detail: `print(f"  {s['start_time'][:16]} | {s['duration_minutes']:.1f} min | {s['n_tracks']} tracks")`
- Print final summaries: `print(f"\nResumen: {len(sessions)} sesiones insertadas en sessions.")`
- Error logging: `print(f"\nERROR: {e}")`
- Warning handling via GitHub Actions annotations: `::warning::` format in `scripts/run_pipeline.py`

## Comments

**When to Comment:**
- Rationale for design decisions: Why session_id uses uuid5 (makes upsert idempotent)
- Algorithm explanation: How `cumsum()` on is_new_session flags creates session numbering
- Non-obvious logic gates: Why duration-gated scoring prevents false routine matches
- Link to external documentation: ADR references in `transformation/label_activities.py`

**JSDoc/TSDoc:**
- Module-level docstrings explaining purpose and usage:
  ```python
  """
  Construccion de sesiones desde raw_plays.
  
  Una sesion es un bloque continuo de escucha...
  
  Uso:
      python transformation/build_sessions.py
  """
  ```

- Function docstrings with Args, Returns sections:
  ```python
  def make_session_id(start_time: pd.Timestamp) -> str:
      """
      Genera un UUID deterministico basado en el start_time de la sesion.
      """
  ```

- Inline comments explaining gates and thresholds (see `label_activities.py` rule functions)

## Function Design

**Size:** Functions typically 10-40 lines. Transformation pipeline broken into focused helpers:
- `assign_sessions()` - handle session boundary logic only
- `build_session_records()` - format session dict only
- `detect_skips()` - classify tracks only
- `upsert_features()` - database write only

**Parameters:**
- Prefer single DataFrame parameter for data processing: `assign_sessions(df: pd.DataFrame) -> pd.DataFrame`
- Avoid globals; pass connections explicitly: `def load_plays(conn) -> pd.DataFrame:`
- Use keyword arguments for optional params: `def load_top_tracks(engine, limit: int = 10) -> pd.DataFrame:`

**Return Values:**
- Transformation functions return modified DataFrames: `assign_sessions()` returns copy with new columns
- Database readers return dictionaries or DataFrames: `load_kpis()` returns `dict`, `load_sessions()` returns `pd.DataFrame`
- Writers return row counts or None: `upsert_sessions()` returns `cursor.rowcount`
- Pipeline scripts return summary dicts: `run()` returns `{"sessions_built": len(sessions)}`

## Module Design

**Exports:**
- One public `run()` function per transformation/ingestion module (entry point)
- Private helper functions with underscore prefix: `_plays()` factory in tests, `_format_markdown_table()` in run_pipeline
- Re-exported imports for convenience: `db/connection.py` exports both `get_connection()` and `get_engine()`

**Barrel Files:**
- No barrel files (index.py exports) used
- Direct imports from modules: `from transformation.build_sessions import assign_sessions`
- Dashboard imports from queries module: `from dashboard.queries import load_kpis, load_sessions, ...`

## Special Patterns

**Caching in Streamlit:**
- `@st.cache_resource` for expensive resources (engine): `@st.cache_resource(show_spinner=False)`
- `@st.cache_data` for query results: `@st.cache_data(ttl=3600)` (1-hour TTL for dashboard data)
- Caching logic isolated in `dashboard/queries.py`

**SQL Query Style:**
- Multi-line query strings with triple quotes: SQL formatted for readability
- Parameterized queries with `%(name)s` placeholders: `psycopg2.extras.execute_batch()`
- Column aliasing for clarity: `SELECT ... AS total_plays`
- Timezone handling in SQL: `AT TIME ZONE 'America/Bogota'` shifts UTC to local time

**Test Fixtures:**
- Helper factories in test files: `_plays()`, `_session()` build DataFrames with required columns
- No external test data files; factories generate inline
- Monkeypatch for environment variables: `monkeypatch.setenv("GITHUB_ACTIONS", "true")`

---

*Convention analysis: 2026-04-15*
