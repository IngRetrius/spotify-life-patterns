# Technology Stack

**Analysis Date:** 2026-04-15

## Languages

**Primary:**
- Python 3.12 - All ingestion, transformation, and pipeline orchestration code

## Runtime

**Environment:**
- Python 3.12 - Specified in `runtime.txt`

**Package Manager:**
- pip - Dependencies managed through `requirements.txt`
- Lockfile: Not detected (uses `requirements.txt` with pinned versions)

## Frameworks

**Core Data:**
- spotipy 2.24.0 - OAuth 2.0 client for Spotify Web API
- pandas 2.2.3 - Data transformation and manipulation
- SQLAlchemy 2.0.36 - ORM and SQL query construction for Supabase

**Database Access:**
- psycopg2-binary 2.9.10 - Native PostgreSQL adapter (used by ingestion/transformation scripts)

**Dashboard & Visualization:**
- streamlit 1.40.2 - Web framework for dashboard at `dashboard/app.py`
- plotly 5.24.1 - Interactive charts in dashboard

**Testing:**
- pytest 9.0.3 - Test framework for transformation layer validation

**Utilities:**
- python-dotenv 1.0.1 - Environment variable management
- tenacity 9.0.0 - Retry logic with exponential backoff for API calls

## Key Dependencies

**Critical:**
- spotipy 2.24.0 - Provides OAuth token refresh via SpotifyOAuth and retry mechanism; used in `ingestion/ingest_plays.py`, `ingestion/ingest_artists.py`, `ingestion/ingest_audio_features.py`
- SQLAlchemy 2.0.36 - Required for `pandas.read_sql()` in dashboard; manages connection pooling with Streamlit's `@st.cache_resource`
- psycopg2-binary 2.9.10 - Raw database connections in pipeline scripts for batch upsert operations

**Infrastructure:**
- tenacity 9.0.0 - Implements retry logic with Retry-After header handling in Spotify API calls (e.g., rate limit 429 responses)

## Configuration

**Environment:**
- `.env.example` documents required env vars:
  - `SPOTIFY_CLIENT_ID` - OAuth client ID from Spotify Developer Dashboard
  - `SPOTIFY_CLIENT_SECRET` - OAuth client secret
  - `SPOTIFY_REDIRECT_URI` - OAuth callback URL (default: `http://127.0.0.1:8888/callback`)
  - `SUPABASE_DB_PASSWORD` - PostgreSQL connection password
- `.cache` file - Stores Spotify OAuth token (created by spotipy; Git-ignored)

**Build:**
- `.streamlit/config.toml` - Streamlit UI theme and visual configuration
  - Primary color: `#1DB954` (Spotify green)
  - Light theme with sans-serif font

**Dashboard Secrets Management:**
- Local dev: Env vars from `.env`
- GitHub Actions: Repository secrets (SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI, SUPABASE_DB_PASSWORD, SPOTIFY_CACHE)
- Streamlit Cloud: Secrets via Streamlit Cloud console (via `st.secrets` fallback in `db/connection.py`)

## Platform Requirements

**Development:**
- Python 3.12
- Virtual environment (`.venv`)
- Dev Container support (Codespaces-compatible image: `mcr.microsoft.com/devcontainers/python:1-3.11-bookworm`)
- PostgreSQL/Supabase connection via internet

**Production/Deployment:**
- **Ingestion Pipeline:** GitHub Actions (Ubuntu latest)
  - Runs on schedule: every 6 hours (cron: `0 */6 * * *`)
  - Can be manually triggered (`workflow_dispatch`)
  - 10-minute timeout limit
- **Dashboard:** Streamlit Community Cloud
  - Deployed from GitHub repository
  - Accessed at: `https://spotify-life-patterns.streamlit.app/`

---

*Stack analysis: 2026-04-15*
