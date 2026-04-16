# Architecture

**Analysis Date:** 2026-04-15

## Pattern Overview

**Overall:** Medallion Architecture (Raw → Analytics) with Batch ETL Pipeline

**Key Characteristics:**
- **Medallion pattern** separates raw API data from processed analytics tables
- **Idempotent transformations** using deterministic UUIDs (uuid5) enable safe re-runs
- **Layered pipeline** with sequential steps that can be partially re-executed (e.g., skip ingestion, run transformation only)
- **Loose coupling** between layers: SQL queries pull from previous layer, no direct function calls across modules
- **Stateless transformers** process entire datasets at each step; no incremental state tracking

## Layers

**Ingestion Layer:**
- Purpose: Fetch data from Spotify Web API and store unchanged in raw tables
- Location: `ingestion/`
- Contains: Three independent ingest modules (plays, audio_features, artists)
- Depends on: Spotify API (via spotipy), PostgreSQL raw tables
- Used by: Direct invocation from run_pipeline.py

**Transformation Layer:**
- Purpose: Build sessions from plays, compute aggregates, infer activity labels
- Location: `transformation/`
- Contains: Three sequential transformation modules (build_sessions, compute_features, label_activities)
- Depends on: Raw layer tables, pandas for in-memory computation
- Used by: Direct invocation from run_pipeline.py
- Key pattern: Each module loads relevant raw/analytics tables into DataFrames, processes in memory, writes back to analytics tables via upsert

**Analytics Layer (Database):**
- Purpose: Curated, processed data ready for queries and visualization
- Location: Schema inside Supabase PostgreSQL (`sessions`, `session_features`, `activity_labels`)
- Contains: Derived tables built from raw layer via transformation scripts
- Depends on: Raw layer tables
- Used by: Dashboard queries (read-only)

**Dashboard Layer:**
- Purpose: Real-time visualization of listening patterns and inferred activities
- Location: `dashboard/`
- Contains: Streamlit UI (app.py) and SQL query layer (queries.py)
- Depends on: Analytics layer tables
- Used by: End users; deployed on Streamlit Community Cloud

## Data Flow

**Complete Pipeline (6 Steps):**

1. **Ingest Plays** (`ingestion/ingest_plays.py`)
   - Spotify API (get_spotify_client) → fetch up to 50 most recent tracks via `/me/player/recently-played`
   - Parse response into flat structure (track_id, artist_id, played_at, etc.)
   - Upsert to `raw_plays` with UNIQUE constraint on (track_id, played_at) → deduplication automatic

2. **Ingest Audio Features** (`ingestion/ingest_audio_features.py`)
   - For each unique track in raw_plays, call `/audio-features` (currently returns 403 — API restricted since 2024)
   - Results stored as mostly-NULL in `raw_audio_features`

3. **Ingest Artists** (`ingestion/ingest_artists.py`)
   - For each unique artist in raw_plays, call `/artists` to get metadata and genres
   - Store in `raw_artists` (currently NULL fields due to API restriction)

4. **Build Sessions** (`transformation/build_sessions.py`)
   - Load all plays from raw_plays into DataFrame, sorted by played_at
   - Calculate gaps between consecutive plays
   - Mark session boundaries where gap > 30 minutes
   - Generate deterministic session_id (uuid5) from start_time (idempotent re-runs safe)
   - Compute session metadata (start_time, end_time, duration_minutes, n_tracks, hour_of_day, day_of_week)
   - Upsert to `sessions`

5. **Compute Features** (`transformation/compute_features.py`)
   - Load sessions, raw_plays, raw_audio_features, raw_artists
   - Assign each play to its session using merge_asof (time-range join)
   - Aggregate per session: n_skips (tracks < 50% listened), avg BPM/energy/valence, dominant_genre
   - Upsert to `session_features`

6. **Label Activities** (`transformation/label_activities.py`)
   - Load sessions with features
   - Apply heuristic scoring rules per activity type (shower, gym, tasks, casual)
   - Each rule: duration gate (mandatory band) + secondary signals (hour, skips)
   - Winner-take-all: highest confidence score wins
   - Fallback to 'unknown' if no rule reaches 0.4 confidence threshold
   - Upsert to `activity_labels`

**State Management:**
- No external state files; entire pipeline history lives in database
- Re-runs are safe because:
  - raw tables use ON CONFLICT DO NOTHING (upsert semantics)
  - analytics tables use deterministic IDs + upsert
  - Sessions rebuild from scratch every run (entire raw_plays dataset reprocessed)

## Key Abstractions

**Session ID (UUID5):**
- Purpose: Stable identifier for sessions across re-runs
- Implementation: `uuid5(NAMESPACE_URL, start_time.isoformat())`
- Pattern: Same inputs always produce same ID → upsert is truly idempotent
- Located in: `transformation/build_sessions.py::make_session_id()`

**Idempotent Upsert:**
- Purpose: Safely re-run entire pipeline without duplicates or orphaned records
- Pattern: INSERT ... ON CONFLICT (unique_constraint) DO NOTHING
- Used by: All ingestion and transformation steps
- Examples:
  - `raw_plays`: UNIQUE (track_id, played_at)
  - `sessions`, `session_features`, `activity_labels`: PRIMARY KEY (session_id)

**Activity Heuristic Rules:**
- Purpose: Convert continuous features (duration, hour, skips) into categorical labels
- Pattern: Duration-gated rules (base score only if duration band matches)
- Examples:
  - Shower: 5–20 min duration, 0 skips, 6–10 AM or 8–11 PM → confidence up to 1.0
  - Gym: 35–110 min duration, ≤2 skips, 5–10 AM or 4–10 PM
  - Tasks: 40–300 min duration, ≤5 skips, 10 PM–5 AM
  - Casual: <5 min OR ≤2 tracks (any session)
- Located in: `transformation/label_activities.py`

**Cursor-Based Pagination:**
- Purpose: Fetch more than 50 tracks in single run (Spotify API limit)
- Pattern: Use 'before' cursor to walk history backward in time
- Located in: `ingestion/ingest_plays.py::fetch_recent_plays()`

## Entry Points

**Pipeline Orchestrator:**
- Location: `scripts/run_pipeline.py::run()`
- Triggers: GitHub Actions (cron every 6 hours) or manual `python scripts/run_pipeline.py`
- Responsibilities:
  - Load step functions lazily (defers spotipy import until needed)
  - Count rows before/after each step for observability
  - Catch exceptions per step and halt on first failure
  - Emit GitHub Actions workflow annotations (::warning::, $GITHUB_STEP_SUMMARY)
  - Allow partial re-runs via `--from N` (e.g., skip ingestion, run transformation only)

**Database Migration:**
- Location: `db/migrate.py::main()`
- Triggers: Manual `python db/migrate.py` (called first-time setup)
- Responsibilities:
  - Bootstrap schema_migrations table
  - Discover .sql files in migrations/ (lexically sorted by prefix)
  - Execute pending migrations, record versions
  - Fallback connection strategy (try pooler txn, pooler session, direct in order)

**Dashboard:**
- Location: `dashboard/app.py` (main Streamlit file)
- Triggers: `streamlit run dashboard/app.py` (local) or auto-deployed to Streamlit Cloud
- Responsibilities:
  - Configure page layout, CSS, caching
  - Call query functions (load_kpis, load_sessions, etc.) from queries.py
  - Render charts (Plotly), KPI cards, session tables
  - Cache database engine across reruns, cache query results for 3 hours

## Error Handling

**Strategy:** Fail-fast with explicit exit codes and error logging

**Patterns:**

1. **Ingestion scripts** (`ingest_*.py`):
   - Retry on HTTP 429 (rate limit) with exponential backoff
   - Catch SpotifyException, log, exit(1) on non-429 errors
   - Use try-except with conn.rollback() in finally block

2. **Transformation scripts** (`transformation/*.py`):
   - Assume input tables exist (no defensive checks; schema bootstrap is migration's job)
   - Catch generic Exception, log, exit(1)
   - Use try-except with conn.rollback() in finally block

3. **Pipeline orchestrator** (`scripts/run_pipeline.py`):
   - Catch SystemExit from individual steps (indicates step failed)
   - Mark step status as "failed", stop pipeline, exit(1) at end
   - Log all steps to text and markdown tables (stdout, GitHub Actions summary)

4. **Migration runner** (`db/migrate.py`):
   - Rollback entire transaction if any migration fails
   - Print error, exit(1)
   - No partial application

5. **Dashboard** (`dashboard/app.py`):
   - Streamlit caching layers catch exceptions gracefully
   - Missing password raises EnvironmentError (no silent fallback)

## Cross-Cutting Concerns

**Logging:**
- Pattern: Print to stdout with context prefixes (step number, operation)
- Observability: GitHub Actions integration via GITHUB_STEP_SUMMARY, GITHUB_ACTIONS env checks
- Example: "[2/6] Ingest audio features" header, before/after row counts

**Validation:**
- Ingestion: Spotify API response structure assumed valid (spotipy handles schema)
- Transformation: DataFrames validated by pandas operations (index type, column presence)
- Database: Constraints (NOT NULL, UNIQUE, FOREIGN KEY) enforced at schema level

**Authentication:**
- Spotify OAuth: First run opens browser, token cached to `.cache` file
- Supabase: Password resolved from env (local), secrets (Streamlit Cloud)
- Credential sources tried in priority order (no silent fallback to invalid state)

**Connection Management:**
- Shared Supabase connection constants in `db/connection.py`
- Two entry points:
  - `get_connection()`: raw psycopg2 (scripts)
  - `get_engine()`: SQLAlchemy (dashboard, pandas.read_sql)
- Connection pooling via Supabase pooler endpoint (port 6543, transaction mode)

---

*Architecture analysis: 2026-04-15*
