# Spotify Life Patterns

A personal data pipeline that infers daily activity patterns from Spotify listening history.
Built end-to-end: from OAuth ingestion to a live, deployed dashboard.

**Live dashboard:** https://spotify-life-patterns.streamlit.app/

---

## Motivation

Most data portfolio projects rely on pre-packaged datasets from Kaggle or public repositories.
This project takes a different approach: the data is entirely personal.

Spotify listening history reflects real behavior. The time of day you listen, how long a session
lasts, whether you skip tracks — these signals are a proxy for what you are actually doing:
showering in the morning, working out in the evening, or studying late at night.

The goal was to build a production-grade pipeline around data that is genuinely mine, and to
answer a real question: *what is my listening history telling me about my daily routines?*

---

## Architecture

```
Spotify API
    |
    |  OAuth 2.0 + REST (every 6 hours via GitHub Actions)
    v
Ingestion Layer  (Python + spotipy)
    ingest_plays.py          recently played tracks
    ingest_audio_features.py audio features per track
    ingest_artists.py        artist metadata and genres
    |
    |  upsert (idempotent)
    v
Raw Layer  (Supabase / PostgreSQL)
    raw_plays
    raw_audio_features
    raw_artists
    |
    |  batch transformation
    v
Transformation Layer  (Python + pandas)
    build_sessions.py        group plays into sessions (gap < 30 min)
    compute_features.py      aggregate features per session
    label_activities.py      heuristic activity labeling
    |
    |  upsert
    v
Analytics Layer  (Supabase / PostgreSQL)
    sessions
    session_features
    activity_labels
    |
    v
Dashboard  (Streamlit — deployed on Streamlit Community Cloud)
```

The architecture follows the **medallion pattern** (raw -> analytics), uses **idempotent upserts**
throughout, and generates **deterministic session IDs** (UUID5) so the pipeline can be rerun
safely at any time without creating duplicates or orphaned records.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Source | Spotify Web API |
| Ingestion | Python 3.12, spotipy |
| Storage | Supabase (PostgreSQL) |
| Transformation | Python, pandas, SQLAlchemy |
| Orchestration | GitHub Actions (cron every 6 hours) |
| Dashboard | Streamlit, Plotly |
| Deploy | Streamlit Community Cloud |

---

## Project Structure

```
spotify-life-patterns/
|
|- ingestion/
|   |- ingest_plays.py           Fetch last 50 recently played tracks
|   |- ingest_audio_features.py  Fetch BPM, energy, valence per track
|   |- ingest_artists.py         Fetch artist genres and metadata
|
|- transformation/
|   |- build_sessions.py         Group plays into listening sessions
|   |- compute_features.py       Compute per-session aggregates and skip count
|   |- label_activities.py       Assign activity label with confidence score
|
|- dashboard/
|   |- app.py                    Streamlit layout and UI
|   |- queries.py                SQL queries (separated from UI logic)
|
|- db/
|   |- migrate.py                Lightweight migration runner (no extra dependencies)
|
|- migrations/
|   |- 001_initial_schema.sql    Full database schema
|
|- scripts/
|   |- run_pipeline.py           Orchestrator: runs all 6 steps in sequence
|
|- docs/
|   |- decisions/                Architecture decision records
|       |- db_design.md
|       |- spotify_api.md
|       |- audio_features_restriction.md
|       |- transformation_layer.md
|
|- .github/workflows/
|   |- ingest.yml                GitHub Actions workflow
|
|- Arquitectura.png              Architecture diagram
|- requirements.txt
|- runtime.txt                   Python 3.12 pin for Streamlit Cloud
|- .env.example                  Environment variable template
```

---

## Activity Labeling

Sessions are classified into three activities using heuristic rules.
Each rule scores 0 to 1 based on conditions met; the highest score wins.
Sessions below 0.4 confidence are labeled `unknown`.

| Activity | Primary signal | Hour bonus |
|---|---|---|
| Shower (ducha) | Duration 5–20 min, zero skips | 6–10 AM or 8–11 PM |
| Gym (gimnasio) | Duration 35–110 min, <= 2 skips | 5–10 AM or 4–10 PM |
| Study/Work (tareas) | Duration > 40 min, <= 5 skips | 10 PM – 5 AM |

The hour bonus is the key discriminator between gym and study sessions, which can overlap
significantly in duration. Audio features (BPM, energy) are reserved for a future ML phase
when enough labeled sessions exist to train a classifier.

For more detail: [`docs/decisions/transformation_layer.md`](docs/decisions/transformation_layer.md)

---

## Database Schema

Two logical layers inside a single PostgreSQL instance on Supabase:

**Raw layer** — data as received from the API, never modified
- `raw_plays` — one row per play event (UNIQUE on track_id + played_at)
- `raw_audio_features` — per-track audio features (currently NULL, Spotify API restricted since 2024)
- `raw_artists` — artist name and genres

**Analytics layer** — clean, processed, query-ready
- `sessions` — one row per listening session
- `session_features` — aggregated metrics per session (n_skips, avg BPM, dominant genre)
- `activity_labels` — inferred activity and confidence score per session

Full schema: [`migrations/001_initial_schema.sql`](migrations/001_initial_schema.sql)

---

## Running Locally

**Requirements:** Python 3.12, a Spotify developer app, a Supabase project.

```bash
# 1. Clone and create virtual environment
git clone https://github.com/IngRetrius/spotify-life-patterns.git
cd spotify-life-patterns
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure credentials
cp .env.example .env
# Edit .env with your Spotify and Supabase credentials

# 4. Run database migrations
python db/migrate.py

# 5. Run the full pipeline
python scripts/run_pipeline.py

# 6. Launch the dashboard
.venv\Scripts\streamlit.exe run dashboard/app.py   # Windows
streamlit run dashboard/app.py                      # macOS / Linux
```

### Pipeline steps

```bash
# Run only the transformation (steps 4-6), skipping API calls
python scripts/run_pipeline.py --from 4
```

### First-time Spotify authentication

The first run of `ingest_plays.py` will open a browser window for OAuth authorization.
After granting access, spotipy saves the token to `.cache`. Subsequent runs are headless.

For GitHub Actions, the `.cache` file content must be stored as a repository secret
named `SPOTIFY_CACHE`. See `.github/workflows/ingest.yml` for details.

---

## GitHub Actions

The pipeline runs automatically every 6 hours via GitHub Actions.

Required repository secrets:
- `SPOTIFY_CLIENT_ID`
- `SPOTIFY_CLIENT_SECRET`
- `SPOTIFY_REDIRECT_URI`
- `SUPABASE_DB_PASSWORD`
- `SPOTIFY_CACHE` — contents of the `.cache` file after first OAuth authorization

---

## Known Limitations

**Spotify API restrictions (since 2024):** The `/audio-features` and `/artists` endpoints
return HTTP 403 for new developer apps. Audio features (BPM, energy, valence) and artist
genres are stored as NULL until Spotify lifts this restriction or an alternative source
is integrated. Activity labeling currently relies entirely on temporal signals.

**50-track cap:** The recently-played endpoint returns at most 50 tracks per request.
Running the pipeline every 6 hours prevents data loss for normal listening volumes.
An extended history export (up to 12 months) can be requested directly from Spotify
and loaded via a bulk import script.

---

## Design Decisions

Detailed rationale for each architectural choice is documented in [`docs/decisions/`](docs/decisions/):

- [Database design](docs/decisions/db_design.md) — medallion architecture, UUID5, idempotent upserts
- [Spotify API](docs/decisions/spotify_api.md) — OAuth flow, rate limits, endpoint restrictions
- [Audio features restriction](docs/decisions/audio_features_restriction.md) — graceful degradation strategy
- [Transformation layer](docs/decisions/transformation_layer.md) — session building, skip detection, heuristic rules
