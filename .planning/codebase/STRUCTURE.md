# Codebase Structure

## Root Layout

```
spotify-life-patterns/
├── ingestion/           # Step 1–3: raw data pull from Spotify API
│   ├── ingest_plays.py      # Fetch recently played tracks
│   ├── ingest_artists.py    # Fetch artist metadata
│   └── ingest_audio_features.py  # Fetch audio features (restricted in 2024)
├── transformation/      # Step 4–5: pure pandas transformations
│   ├── build_sessions.py    # Group plays into listening sessions
│   ├── compute_features.py  # Derive skip detection and per-session metrics
│   └── label_activities.py  # Heuristic activity classification
├── dashboard/           # Step 6: Streamlit presentation layer
│   ├── app.py               # Main app with all chart sections
│   └── queries.py           # Supabase read queries with caching
├── db/                  # Database utilities
│   ├── connection.py        # Supabase client singleton
│   └── migrate.py           # Schema migration runner
├── scripts/             # Orchestration
│   └── run_pipeline.py      # End-to-end pipeline runner (steps 1–5)
├── migrations/          # SQL schema files
│   └── 001_initial_schema.sql
├── tests/               # Unit tests (pytest)
│   ├── conftest.py
│   ├── test_build_sessions.py
│   ├── test_compute_features.py
│   ├── test_label_activities.py
│   └── test_run_pipeline.py
├── docs/
│   └── decisions/       # Architecture Decision Records (ADRs)
│       ├── audio_features_restriction.md
│       ├── dashboard_layer.md
│       ├── db_design.md
│       ├── spotify_api.md
│       └── transformation_layer.md
├── .github/
│   └── workflows/
│       └── ingest.yml   # GitHub Actions scheduled pipeline
├── .streamlit/
│   └── config.toml      # Streamlit theme/server config
├── .devcontainer/
│   └── devcontainer.json
├── requirements.txt     # Python dependencies
├── runtime.txt          # Python version pin (for Streamlit Cloud)
├── .env.example         # Required environment variables template
└── Arquitectura.png     # Pipeline architecture diagram
```

## Key Locations

| Location | Purpose |
|----------|---------|
| `transformation/build_sessions.py` | Core session algorithm with `SESSION_GAP_MINUTES=30` |
| `transformation/label_activities.py` | Heuristic rules: shower/gym/tasks/casual/unknown |
| `transformation/compute_features.py` | Skip detection with `SKIP_THRESHOLD=0.5` |
| `dashboard/app.py` | Streamlit multi-section dashboard |
| `dashboard/queries.py` | All Supabase read queries with `@cache_data` TTL |
| `db/connection.py` | Supabase client via `SUPABASE_URL` + `SUPABASE_KEY` |
| `scripts/run_pipeline.py` | Pipeline orchestrator — runs steps in sequence |
| `migrations/001_initial_schema.sql` | Full DB schema definition |
| `.github/workflows/ingest.yml` | Scheduled ingestion (GitHub Actions) |
| `docs/decisions/` | ADRs documenting key architectural choices |

## Naming Conventions

| Scope | Convention | Example |
|-------|-----------|---------|
| Modules | `snake_case` noun phrases | `build_sessions.py`, `ingest_plays.py` |
| Functions | `snake_case` verb phrases | `assign_sessions()`, `detect_skips()` |
| Constants | `UPPER_SNAKE_CASE` | `SESSION_GAP_MINUTES`, `SKIP_THRESHOLD` |
| Test files | `test_{module}.py` | `test_build_sessions.py` |
| Test classes | `Test{Concept}` | `TestAssignSessions`, `TestDurationGate` |
| Test helpers | `_noun()` factory | `_plays()`, `_session()` |
| DB tables | `snake_case` plural | `plays`, `sessions`, `artists` |

## Module Dependency Flow

```
Spotify API
    ↓
ingestion/          (external I/O — Spotify API + Supabase writes)
    ↓
transformation/     (pure functions — pandas only, no I/O)
    ↓
db/                 (Supabase client — connection + migrations)
    ↓
dashboard/          (Streamlit UI — Supabase reads + visualization)
```

`scripts/run_pipeline.py` wires ingestion → transformation → db writes in sequence.

## Configuration Files

| File | Purpose |
|------|---------|
| `.env` | Runtime secrets (not committed) |
| `.env.example` | Template listing required env vars |
| `requirements.txt` | Pinned Python dependencies |
| `runtime.txt` | Python version for Streamlit Cloud deployment |
| `.streamlit/config.toml` | Streamlit theme and server settings |
| `.github/workflows/ingest.yml` | CI/CD for scheduled pipeline execution |

## Documentation

`docs/decisions/` contains ADRs for all significant design choices:
- `db_design.md` — table schema, UUID5 idempotency, upsert strategy
- `transformation_layer.md` — session gap threshold, activity heuristics, canonical test sessions
- `dashboard_layer.md` — Streamlit choice, query caching approach
- `spotify_api.md` — API scope, auth flow, rate limits
- `audio_features_restriction.md` — why audio features ingestion is disabled
