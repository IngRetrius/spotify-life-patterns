<!-- GSD:project-start source:PROJECT.md -->
## Project

**Spotify Life Patterns — Bugfix: Timezone & Cache**

Dashboard de Spotify que extrae plays via API, construye sesiones de escucha, infiere actividades (gym, shower, tasks, casual) con heurísticas, y las visualiza en Streamlit. El pipeline corre en GitHub Actions cada 6 horas. Este milestone cubre dos bugs de correctitud: horas incorrectas en la tabla `sessions` (UTC en vez de UTC-5 Bogotá) y un TTL de cache demasiado largo que impide ver datos frescos al recargar el dashboard.

**Core Value:** El dashboard debe mostrar los patrones de escucha reales del usuario — horas y actividades correctas, datos del pipeline más reciente.

### Constraints

- **Tech**: Python 3.12, pandas, Streamlit 1.40.2, Supabase/PostgreSQL
- **No DB migration**: El fix de timezone se aplica via re-run del pipeline (upsert idempotente)
- **No downtime**: `DO UPDATE SET` permite actualizar en producción sin borrar filas
<!-- GSD:project-end -->

<!-- GSD:stack-start source:codebase/STACK.md -->
## Technology Stack

## Languages
- Python 3.12 - All ingestion, transformation, and pipeline orchestration code
## Runtime
- Python 3.12 - Specified in `runtime.txt`
- pip - Dependencies managed through `requirements.txt`
- Lockfile: Not detected (uses `requirements.txt` with pinned versions)
## Frameworks
- spotipy 2.24.0 - OAuth 2.0 client for Spotify Web API
- pandas 2.2.3 - Data transformation and manipulation
- SQLAlchemy 2.0.36 - ORM and SQL query construction for Supabase
- psycopg2-binary 2.9.10 - Native PostgreSQL adapter (used by ingestion/transformation scripts)
- streamlit 1.40.2 - Web framework for dashboard at `dashboard/app.py`
- plotly 5.24.1 - Interactive charts in dashboard
- pytest 9.0.3 - Test framework for transformation layer validation
- python-dotenv 1.0.1 - Environment variable management
- tenacity 9.0.0 - Retry logic with exponential backoff for API calls
## Key Dependencies
- spotipy 2.24.0 - Provides OAuth token refresh via SpotifyOAuth and retry mechanism; used in `ingestion/ingest_plays.py`, `ingestion/ingest_artists.py`, `ingestion/ingest_audio_features.py`
- SQLAlchemy 2.0.36 - Required for `pandas.read_sql()` in dashboard; manages connection pooling with Streamlit's `@st.cache_resource`
- psycopg2-binary 2.9.10 - Raw database connections in pipeline scripts for batch upsert operations
- tenacity 9.0.0 - Implements retry logic with Retry-After header handling in Spotify API calls (e.g., rate limit 429 responses)
## Configuration
- `.env.example` documents required env vars:
- `.cache` file - Stores Spotify OAuth token (created by spotipy; Git-ignored)
- `.streamlit/config.toml` - Streamlit UI theme and visual configuration
- Local dev: Env vars from `.env`
- GitHub Actions: Repository secrets (SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI, SUPABASE_DB_PASSWORD, SPOTIFY_CACHE)
- Streamlit Cloud: Secrets via Streamlit Cloud console (via `st.secrets` fallback in `db/connection.py`)
## Platform Requirements
- Python 3.12
- Virtual environment (`.venv`)
- Dev Container support (Codespaces-compatible image: `mcr.microsoft.com/devcontainers/python:1-3.11-bookworm`)
- PostgreSQL/Supabase connection via internet
- **Ingestion Pipeline:** GitHub Actions (Ubuntu latest)
- **Dashboard:** Streamlit Community Cloud
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

## Naming Patterns
- Snake_case for all Python files: `ingest_plays.py`, `build_sessions.py`, `compute_features.py`
- Dashboard components: `app.py` (UI), `queries.py` (data layer)
- Test files match source: `test_build_sessions.py` for `transformation/build_sessions.py`
- Snake_case for all function names: `assign_sessions()`, `detect_skips()`, `compute_dominant_genre()`
- Private helpers prefixed with underscore: `_plays()`, `_resolve_password()`, `_format_markdown_table()`
- Public entry points: `run()`, `load_plays()`, `get_connection()`, `get_engine()`
- Snake_case throughout: `total_plays`, `duration_minutes`, `session_num`, `is_new_session`
- Constants in UPPER_CASE: `SESSION_GAP_MINUTES = 30`, `SKIP_THRESHOLD = 0.5`, `POOLER_HOST`
- Boolean variables often prefixed with `is_` or `has_`: `is_skip`, `is_new_session`, `autocommit`
- Type hints used in function signatures: `def load_plays(conn) -> pd.DataFrame:`, `def run() -> dict:`
- Union syntax: `str | None` (Python 3.10+ style)
- Import DataFrame types: `pd.DataFrame`, `pd.Series`, `pd.Timestamp`
## Code Style
- No explicit formatter configured (no .prettierrc or black config found)
- Follows PEP 8 standard indentation (4 spaces)
- Line length appears around 88-100 characters based on existing code
- Docstrings in triple-quoted format (see below)
- No explicit linter configuration found (no .eslintrc or pylintrc)
- Code follows PEP 8 conventions
- Imports organized with standard library first, then third-party
## Import Organization
- No path aliases configured
- Full relative imports used: `from db.connection import get_connection`
- sys.path manipulation in entry points: `sys.path.insert(0, os.path.dirname(...))`
## Error Handling
- Try/except/finally for database operations:
- Explicit error propagation with sys.exit(1) in scripts: `scripts/run_pipeline.py`, ingestion modules
- Rate limit handling in Spotify client with retry logic:
- Environment variable fallback chain: `db/connection.py` checks env vars, then st.secrets, then raises
## Logging
- Print progress markers: `print("=== Construccion de sesiones ===")` 
- Print step results: `print(f"Plays cargados: {len(df)}")`
- Print row-level detail: `print(f"  {s['start_time'][:16]} | {s['duration_minutes']:.1f} min | {s['n_tracks']} tracks")`
- Print final summaries: `print(f"\nResumen: {len(sessions)} sesiones insertadas en sessions.")`
- Error logging: `print(f"\nERROR: {e}")`
- Warning handling via GitHub Actions annotations: `::warning::` format in `scripts/run_pipeline.py`
## Comments
- Rationale for design decisions: Why session_id uses uuid5 (makes upsert idempotent)
- Algorithm explanation: How `cumsum()` on is_new_session flags creates session numbering
- Non-obvious logic gates: Why duration-gated scoring prevents false routine matches
- Link to external documentation: ADR references in `transformation/label_activities.py`
- Module-level docstrings explaining purpose and usage:
- Function docstrings with Args, Returns sections:
- Inline comments explaining gates and thresholds (see `label_activities.py` rule functions)
## Function Design
- `assign_sessions()` - handle session boundary logic only
- `build_session_records()` - format session dict only
- `detect_skips()` - classify tracks only
- `upsert_features()` - database write only
- Prefer single DataFrame parameter for data processing: `assign_sessions(df: pd.DataFrame) -> pd.DataFrame`
- Avoid globals; pass connections explicitly: `def load_plays(conn) -> pd.DataFrame:`
- Use keyword arguments for optional params: `def load_top_tracks(engine, limit: int = 10) -> pd.DataFrame:`
- Transformation functions return modified DataFrames: `assign_sessions()` returns copy with new columns
- Database readers return dictionaries or DataFrames: `load_kpis()` returns `dict`, `load_sessions()` returns `pd.DataFrame`
- Writers return row counts or None: `upsert_sessions()` returns `cursor.rowcount`
- Pipeline scripts return summary dicts: `run()` returns `{"sessions_built": len(sessions)}`
## Module Design
- One public `run()` function per transformation/ingestion module (entry point)
- Private helper functions with underscore prefix: `_plays()` factory in tests, `_format_markdown_table()` in run_pipeline
- Re-exported imports for convenience: `db/connection.py` exports both `get_connection()` and `get_engine()`
- No barrel files (index.py exports) used
- Direct imports from modules: `from transformation.build_sessions import assign_sessions`
- Dashboard imports from queries module: `from dashboard.queries import load_kpis, load_sessions, ...`
## Special Patterns
- `@st.cache_resource` for expensive resources (engine): `@st.cache_resource(show_spinner=False)`
- `@st.cache_data` for query results: `@st.cache_data(ttl=3600)` (1-hour TTL for dashboard data)
- Caching logic isolated in `dashboard/queries.py`
- Multi-line query strings with triple quotes: SQL formatted for readability
- Parameterized queries with `%(name)s` placeholders: `psycopg2.extras.execute_batch()`
- Column aliasing for clarity: `SELECT ... AS total_plays`
- Timezone handling in SQL: `AT TIME ZONE 'America/Bogota'` shifts UTC to local time
- Helper factories in test files: `_plays()`, `_session()` build DataFrames with required columns
- No external test data files; factories generate inline
- Monkeypatch for environment variables: `monkeypatch.setenv("GITHUB_ACTIONS", "true")`
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

## Pattern Overview
- **Medallion pattern** separates raw API data from processed analytics tables
- **Idempotent transformations** using deterministic UUIDs (uuid5) enable safe re-runs
- **Layered pipeline** with sequential steps that can be partially re-executed (e.g., skip ingestion, run transformation only)
- **Loose coupling** between layers: SQL queries pull from previous layer, no direct function calls across modules
- **Stateless transformers** process entire datasets at each step; no incremental state tracking
## Layers
- Purpose: Fetch data from Spotify Web API and store unchanged in raw tables
- Location: `ingestion/`
- Contains: Three independent ingest modules (plays, audio_features, artists)
- Depends on: Spotify API (via spotipy), PostgreSQL raw tables
- Used by: Direct invocation from run_pipeline.py
- Purpose: Build sessions from plays, compute aggregates, infer activity labels
- Location: `transformation/`
- Contains: Three sequential transformation modules (build_sessions, compute_features, label_activities)
- Depends on: Raw layer tables, pandas for in-memory computation
- Used by: Direct invocation from run_pipeline.py
- Key pattern: Each module loads relevant raw/analytics tables into DataFrames, processes in memory, writes back to analytics tables via upsert
- Purpose: Curated, processed data ready for queries and visualization
- Location: Schema inside Supabase PostgreSQL (`sessions`, `session_features`, `activity_labels`)
- Contains: Derived tables built from raw layer via transformation scripts
- Depends on: Raw layer tables
- Used by: Dashboard queries (read-only)
- Purpose: Real-time visualization of listening patterns and inferred activities
- Location: `dashboard/`
- Contains: Streamlit UI (app.py) and SQL query layer (queries.py)
- Depends on: Analytics layer tables
- Used by: End users; deployed on Streamlit Community Cloud
## Data Flow
- No external state files; entire pipeline history lives in database
- Re-runs are safe because:
## Key Abstractions
- Purpose: Stable identifier for sessions across re-runs
- Implementation: `uuid5(NAMESPACE_URL, start_time.isoformat())`
- Pattern: Same inputs always produce same ID → upsert is truly idempotent
- Located in: `transformation/build_sessions.py::make_session_id()`
- Purpose: Safely re-run entire pipeline without duplicates or orphaned records
- Pattern: INSERT ... ON CONFLICT (unique_constraint) DO NOTHING
- Used by: All ingestion and transformation steps
- Examples:
- Purpose: Convert continuous features (duration, hour, skips) into categorical labels
- Pattern: Duration-gated rules (base score only if duration band matches)
- Examples:
- Located in: `transformation/label_activities.py`
- Purpose: Fetch more than 50 tracks in single run (Spotify API limit)
- Pattern: Use 'before' cursor to walk history backward in time
- Located in: `ingestion/ingest_plays.py::fetch_recent_plays()`
## Entry Points
- Location: `scripts/run_pipeline.py::run()`
- Triggers: GitHub Actions (cron every 6 hours) or manual `python scripts/run_pipeline.py`
- Responsibilities:
- Location: `db/migrate.py::main()`
- Triggers: Manual `python db/migrate.py` (called first-time setup)
- Responsibilities:
- Location: `dashboard/app.py` (main Streamlit file)
- Triggers: `streamlit run dashboard/app.py` (local) or auto-deployed to Streamlit Cloud
- Responsibilities:
## Error Handling
## Cross-Cutting Concerns
- Pattern: Print to stdout with context prefixes (step number, operation)
- Observability: GitHub Actions integration via GITHUB_STEP_SUMMARY, GITHUB_ACTIONS env checks
- Example: "[2/6] Ingest audio features" header, before/after row counts
- Ingestion: Spotify API response structure assumed valid (spotipy handles schema)
- Transformation: DataFrames validated by pandas operations (index type, column presence)
- Database: Constraints (NOT NULL, UNIQUE, FOREIGN KEY) enforced at schema level
- Spotify OAuth: First run opens browser, token cached to `.cache` file
- Supabase: Password resolved from env (local), secrets (Streamlit Cloud)
- Credential sources tried in priority order (no silent fallback to invalid state)
- Shared Supabase connection constants in `db/connection.py`
- Two entry points:
- Connection pooling via Supabase pooler endpoint (port 6543, transaction mode)
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->
## Project Skills

No project skills found. Add skills to any of: `.claude/skills/`, `.agents/skills/`, `.cursor/skills/`, or `.github/skills/` with a `SKILL.md` index file.
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
