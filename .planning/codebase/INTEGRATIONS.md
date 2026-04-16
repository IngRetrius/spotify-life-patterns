# External Integrations

**Analysis Date:** 2026-04-15

## APIs & External Services

**Spotify Web API:**
- Service: Spotify Web API (https://api.spotify.com)
- What it's used for: Ingestion of user's listening history, track metadata, audio features, and artist information
  - SDK/Client: spotipy 2.24.0
  - Auth: OAuth 2.0 (SpotifyOAuth) with scope `user-read-recently-played`
  - Endpoints used:
    - `/v1/me/player/recently-played` - Fetch 50 most recent tracks with cursor pagination
    - `/v1/audio-features` - Fetch audio features (BPM, energy, valence, etc.) for up to 100 tracks per call
    - `/v1/artists` - Fetch artist metadata and genres for up to 50 artists per call
  - Rate limit handling: Exponential backoff with `tenacity` and Retry-After header (429 responses)
  - Token caching: Credentials cached in `.cache` file (persisted in GitHub Actions via `secrets.SPOTIFY_CACHE`)
- Implementation files: `ingestion/ingest_plays.py`, `ingestion/ingest_audio_features.py`, `ingestion/ingest_artists.py`

## Data Storage

**Databases:**
- Provider: Supabase (PostgreSQL-compatible)
  - Connection: Pooler endpoint at `aws-1-us-east-1.pooler.supabase.com:6543` (transaction pooler mode for free tier)
  - Project reference: `ofjjslcrzzllzaiiygya`
  - Auth: PostgreSQL user `postgres.{PROJECT_REF}` with password from `SUPABASE_DB_PASSWORD`
  - SSL: Enforced (`sslmode=require`)
  - Client: psycopg2-binary (raw connections) + SQLAlchemy (ORM for dashboard)
  
**Raw Layer Tables** (source data from Spotify):
- `raw_plays` - 50 most recent tracks with played_at timestamps
  - Unique constraint: (track_id, played_at) for idempotent upsert
- `raw_audio_features` - Audio features (tempo, energy, danceability, etc.) per track
  - Primary key: track_id
- `raw_artists` - Artist metadata including genres and popularity
  - Primary key: artist_id

**Analytics Layer Tables** (derived/transformed):
- `sessions` - Listening sessions grouped by 30-minute gaps
  - Deterministic session_id (UUID5) for idempotent reruns
- `session_features` - Aggregated audio features per session
  - Foreign key to sessions (ON DELETE CASCADE)
- `activity_labels` - Inferred activity labels (shower, workout, study, etc.) with confidence scores
  - Foreign key to sessions (ON DELETE CASCADE)
  - Labeling method: heuristic (based on time of day, BPM, energy, valence)

**Connection strategy:**
- Local dev / CI: `get_connection()` returns raw psycopg2 for ingestion/transformation
- Dashboard: `get_engine()` returns SQLAlchemy engine, cached with `@st.cache_resource`
- Password resolution (in `db/connection.py`):
  1. Environment variable `SUPABASE_DB_PASSWORD`
  2. Streamlit Cloud secrets via `st.secrets["SUPABASE_DB_PASSWORD"]`
  3. Raises error if neither available (no fallback)

**File Storage:**
- `.cache` - Spotify OAuth token cache (Git-ignored, restored from GitHub Actions secret)
- Local filesystem only; no S3 or cloud storage integration

**Caching:**
- Streamlit: `@st.cache_resource` (database engine), `@st.cache_data` (query results with 3-hour TTL)
- Spotify token: OAuth token cached to `.cache` for reuse across runs

## Authentication & Identity

**Auth Provider:**
- Spotify OAuth 2.0
  - Flow: Authorization Code (user redirected to Spotify, returns code, client exchanges for access token)
  - Scope required: `user-read-recently-played`
  - Token expiry: Access tokens expire after ~1 hour; spotipy auto-refreshes using refresh token stored in `.cache`
  - Redirect URI: `http://127.0.0.1:8888/callback` (local) / configured per deployment environment
- Implementation: `spotipy.oauth2.SpotifyOAuth` in `ingestion/ingest_plays.py`, `ingestion/ingest_artists.py`, `ingestion/ingest_audio_features.py`

**Supabase Database Auth:**
- PostgreSQL username/password
  - Username: `postgres.{PROJECT_REF}` (constant)
  - Password: Injected via `SUPABASE_DB_PASSWORD` (environment variable or Streamlit secret)
  - Connection pooling via Supabase's transaction pooler (port 6543)

## Monitoring & Observability

**Error Tracking:**
- Not detected - No Sentry or structured error tracking service integrated

**Logs:**
- Print statements to stdout (scripts: `ingestion/`, `transformation/`, `scripts/run_pipeline.py`)
- GitHub Actions: Output captured in workflow logs and `$GITHUB_STEP_SUMMARY` markdown summary
  - `run_pipeline.py` formats step-by-step results as markdown table and appends to summary
  - Warning annotations emitted for suspicious conditions (e.g., 0 new plays ingested)

**Pipeline Observability:**
- `scripts/run_pipeline.py` counts rows in target tables before/after each step
- Reports: Markdown table with step name, status, row counts, delta, and duration
- Visible on GitHub Actions run page without digging into logs

## CI/CD & Deployment

**Hosting:**
- Ingestion Pipeline: GitHub Actions (Ubuntu latest)
  - Triggers: Schedule (every 6 hours: `0 */6 * * *`) + manual via `workflow_dispatch`
- Dashboard: Streamlit Community Cloud
  - Live at: `https://spotify-life-patterns.streamlit.app/`
  - Auto-deploys from main branch

**CI Pipeline:**
- Workflow: `.github/workflows/ingest.yml`
  - Checkout repository → Setup Python 3.12 → Install dependencies
  - Run pytest tests (transformation layer validation, no DB access)
  - Restore Spotify token cache from `secrets.SPOTIFY_CACHE`
  - Run full 6-step pipeline (`scripts/run_pipeline.py`)
  - Emit summary to `$GITHUB_STEP_SUMMARY` and warnings if needed
  - Timeout: 10 minutes
- Test command: `python -m pytest tests/ -v`
- Pipeline command: `python scripts/run_pipeline.py`

## Environment Configuration

**Required env vars:**
- `SPOTIFY_CLIENT_ID` - Spotify OAuth client ID
- `SPOTIFY_CLIENT_SECRET` - Spotify OAuth client secret
- `SPOTIFY_REDIRECT_URI` - Spotify OAuth callback URL
- `SUPABASE_DB_PASSWORD` - PostgreSQL password

**Secrets location:**
- Local dev: `.env` file (Git-ignored)
- GitHub Actions: Repository secrets (`Settings > Secrets and variables > Actions`)
  - Secrets: `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, `SPOTIFY_REDIRECT_URI`, `SUPABASE_DB_PASSWORD`, `SPOTIFY_CACHE`
- Streamlit Cloud: Managed via Streamlit Cloud console (accessed via `st.secrets`)

**Configuration files:**
- `.env.example` - Template for local env vars
- `.streamlit/config.toml` - UI theme, colors, font
- `.cache` - Spotify token (auto-created, Git-ignored)

## Webhooks & Callbacks

**Incoming:**
- None detected

**Outgoing:**
- Spotify OAuth redirect URI: `http://127.0.0.1:8888/callback` (local development only; OAuth code exchange happens here)

## Data Flow & Idempotency

**Pipeline Design:**
1. **Ingestion** (steps 1-3): Fetch from Spotify API → upsert to raw layer
   - Spotify data extracted with `spotipy` → parsed in Python → upsert via `psycopg2` with `ON CONFLICT DO NOTHING`
   - Idempotent: (track_id, played_at) unique constraint prevents duplicates

2. **Transformation** (steps 4-6): Read raw tables → compute analytics → upsert to analytics layer
   - Read raw_plays, raw_audio_features, raw_artists via SQL/pandas
   - Python + pandas for session grouping, feature aggregation, activity labeling
   - Upsert to sessions, session_features, activity_labels with UUID5 deterministic session IDs
   - Idempotent: Session ID computed from track IDs and timestamps (reproducible)

3. **Dashboard**: Query analytics layer via SQLAlchemy + pandas
   - Queries cached with Streamlit `@st.cache_data` (3-hour TTL for load_kpis, load_sessions, etc.)
   - Real-time reads on page load; no manual refresh needed due to caching

---

*Integration audit: 2026-04-15*
