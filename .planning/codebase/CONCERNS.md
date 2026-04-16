# Codebase Concerns

**Analysis Date:** 2026-04-15

## Tech Debt

**SQL Injection Risk in Pipeline Monitoring:**
- Issue: `scripts/run_pipeline.py` line 74 uses f-string interpolation for table names in `_count_rows()` function: `cur.execute(f"SELECT COUNT(*) FROM {table}")`. While table names are passed from controlled constants, this pattern is not parameterized.
- Files: `scripts/run_pipeline.py:74`
- Impact: Potential SQL injection vulnerability if table name variable is ever sourced from external input or configuration
- Fix approach: Use parameterized queries with pg_identifier or build a whitelist of valid table names with explicit mapping

**Deprecated Spotify API Endpoints:**
- Issue: Audio features endpoint (`/audio-features`) and artist metadata fields (`genres`, `popularity`) are marked deprecated by Spotify and have restricted access for new developer apps since 2024
- Files: `ingestion/ingest_audio_features.py:5-16`, `ingestion/ingest_artists.py:10-13`, `dashboard/app.py:461-465`, `transformation/compute_features.py:6-9`
- Impact: Audio features stored as NULL in database; `dominant_genre` in session features cannot be computed; labeling relies solely on temporal signals (hour_of_day, duration_minutes, n_skips, n_tracks)
- Workaround: Current code handles 403/404 gracefully and continues pipeline without features
- Fix approach: Consider alternative genre data sources (Last.fm, MusicBrainz) or remove audio features entirely from schema and queries if unused

**Missing Comprehensive Error Context:**
- Issue: Exception handlers catch and exit broadly (`except Exception as e`) without logging stack traces or context beyond the error message
- Files: `db/connection.py:55`, `scripts/run_pipeline.py:79`, `scripts/run_pipeline.py:140`, `transformation/build_sessions.py:188`, `transformation/compute_features.py:244`, `transformation/label_activities.py:255`
- Impact: Difficult to diagnose root causes of pipeline failures in production; error details lost after rollback
- Fix approach: Use proper logging module with stack traces; store error context (rows processed, state) before exit

**Console-Only Logging (No Structured Logs):**
- Issue: All logging uses `print()` statements; no structured logging framework (logging module)
- Files: `db/migrate.py`, `ingestion/ingest_*.py`, `transformation/*.py`, `scripts/run_pipeline.py`
- Impact: No centralized log collection, filtering, or searching in production; GitHub Actions integration relies on parsing stdout
- Fix approach: Introduce Python `logging` module with file handlers; keep print() for immediate feedback but log all operations to rotating file logs

## Known Bugs & Limitations

**Silent Data Loss on Tracks Without Features:**
- Symptoms: Tracks with `None` response from Spotify `/audio-features` endpoint are skipped entirely in `fetch_audio_features()` (line 120 `if item is None: continue`)
- Files: `ingestion/ingest_audio_features.py:120-123`
- Trigger: Fetch audio features for track IDs that are local tracks, very new, or from restricted content
- Impact: These tracks are never stored in `raw_audio_features`, and if the table is queried elsewhere, they silently vanish
- Workaround: Current logic works because NULL values are accepted in raw_audio_features; compute_features.py handles missing joins
- Better approach: Explicitly insert a row with track_id but all features NULL so the track is tracked as "attempted"

**Incomplete Genre Extraction on Artist Fetch Failure:**
- Symptoms: If Spotify `/artists` endpoint returns 403 (deprecated), artist metadata falls back to name-only from raw_plays, no genres stored
- Files: `ingestion/ingest_artists.py:128-136`
- Impact: `dominant_genre` in session_features will always be NULL; activity labeling cannot use genre signal
- Workaround: Hardcoded fallback stores artist_name; pipeline continues
- Acceptable: Genre-based labeling never implemented; heuristics use temporal signals only

**No Validation of Parsed Spotify Response Structure:**
- Symptoms: Code assumes Spotify API response structure matches expected format (e.g., `response.get("items")`, `track["id"]`)
- Files: `ingestion/ingest_plays.py:86-107`, `ingestion/ingest_artists.py:105-121`, `ingestion/ingest_audio_features.py:115-137`
- Impact: If API schema changes unexpectedly (missing fields, renamed keys), parsing silently produces empty or malformed records
- Fix approach: Add schema validation or type checking on API responses before parsing

## Security Considerations

**Spotify Credentials in Spotipy Cache File:**
- Risk: SpotifyOAuth stores access tokens in `.cache` file (default filename) in project root
- Files: `ingestion/ingest_plays.py:52`, `ingestion/ingest_audio_features.py:50`, `ingestion/ingest_artists.py:49`
- Current mitigation: `.gitignore` should exclude `.cache`; `.cache` is per-user and not tracked
- Recommendations:
  - Verify `.cache` is in `.gitignore` (essential for CI safety)
  - Consider using XDG_CACHE_HOME environment variable to move cache outside project
  - Add warning in setup docs not to commit `.cache`

**Database Password in Connection Strings (Temporary):**
- Risk: `db/connection.py:85-90` constructs SQLAlchemy URL with raw password; URL may appear in debug logs or error messages
- Files: `db/connection.py:85-90`
- Current mitigation: URL is only used to create engine; not logged or passed externally
- Recommendations:
  - Ensure error messages never print the full URL
  - Verify Supabase connection tests don't capture password in output
  - Use SQLAlchemy create_engine safe parameter handling (already done with function return)

**No Rate-Limiting Guard on Concurrent Pipeline Runs:**
- Risk: If `run_pipeline.py` is triggered multiple times concurrently (e.g., multiple CI runners), Spotify API calls could exceed rate limits without backoff coordination
- Files: `ingestion/ingest_plays.py:72-83` (per-process retry), `ingestion/ingest_artists.py:103-127` (per-process retry), `ingestion/ingest_audio_features.py:114-157` (per-process retry)
- Current mitigation: Individual retries handle 429 response with exponential backoff; ON CONFLICT in inserts means duplicate rows are safe
- Recommendations:
  - Document that pipeline should not run concurrently
  - Add concurrency guard in CI (e.g., `concurrency: group` in GitHub Actions)
  - Consider Redis-based distributed lock if multi-process Spotify fetching is needed

**Environment Variable Exposure in Streamlit Secrets:**
- Risk: `db/connection.py:54` reads `st.secrets["SUPABASE_DB_PASSWORD"]` on Streamlit Cloud; Streamlit stores secrets in environment
- Files: `db/connection.py:40-64`
- Current mitigation: Secrets are encrypted in Streamlit Cloud, loaded at runtime, not persisted to disk
- Recommendations:
  - Verify Streamlit Cloud secret rotation practices
  - Document that Streamlit secrets should use restricted service accounts (IP allowlist on Supabase if possible)

## Performance Bottlenecks

**Large DataFrame Joins in Memory (compute_features.py):**
- Problem: `merge_asof()` on full sessions and plays DataFrames happens in memory
- Files: `transformation/compute_features.py:74-98`
- Cause: For large datasets (millions of plays), memory footprint scales with data size; no streaming or chunking
- Impact: Pipeline may crash on Streamlit Cloud (256 MB memory limit) or slow significantly on local machines with >500k plays
- Improvement path:
  - Move merge logic to SQL: `SELECT ... FROM plays JOIN sessions ON ...`
  - If done in-memory, chunk plays into batches and process iteratively
  - Monitor memory usage with large datasets

**N+1 Query on Session Detail Page:**
- Problem: `dashboard/app.py` calls `_plays_for_day(selected_day)` and separately `_sessions()` then filters locally
- Files: `dashboard/app.py:322-326`
- Cause: Two separate SQL queries instead of a single JOIN; filtering in Python instead of database
- Impact: Loads all sessions in memory even when only one day is needed; scales poorly with large history
- Improvement path:
  - Refactor `load_plays_for_day()` to also load associated sessions in single query
  - Or add `load_sessions_for_day()` function to queries.py and use it instead

**Repeated Full Aggregations in KPI Queries:**
- Problem: `load_kpis()` runs three separate queries (raw_plays count, sessions count, top activity) sequentially
- Files: `dashboard/queries.py:29-65`
- Cause: Each aggregation hits the database separately
- Impact: Three round-trips to database on page load; could be 1 with UNION or combined CTE
- Improvement path: Combine queries into single statement or CTE for atomic snapshot

**3-Hour TTL on All Cache Queries:**
- Problem: Hardcoded `@st.cache_data(ttl=timedelta(hours=3))` on all dashboard queries means stale data for 3 hours after ingestion
- Files: `dashboard/app.py:125-164`
- Cause: Cache decorator applied uniformly regardless of data change frequency
- Impact: Users see outdated statistics immediately after pipeline runs; no way to refresh without reloading page
- Improvement path:
  - Add explicit "Refresh" button that clears cache
  - Differentiate TTLs: static data (top tracks) longer; dynamic data (sessions) shorter or cache-invalidated on ingestion
  - Consider streaming updates if real-time is important

## Fragile Areas

**Session ID Determinism Depends on Timestamp Precision:**
- Files: `transformation/build_sessions.py:60-67`
- Why fragile: Session ID is `uuid5(NAMESPACE, start_time.isoformat())`. If start_time precision changes (e.g., microseconds dropped), UUID changes and upsert treats it as new row
- Safe modification:
  - Never modify `start_time` assignment logic without updating this comment
  - If reparsing plays with different timestamp resolution, sessions will duplicate (not break, but will create confusion)
  - Test confirms: `test_build_sessions.py` checks session ID consistency
- Test coverage: `tests/test_build_sessions.py:20-50` (good)

**Activity Labeling Thresholds Are Hardcoded Magic Numbers:**
- Files: `transformation/label_activities.py:47-67`
- Why fragile:
  - SHOWER_DURATION=(5, 20), GYM_DURATION=(35, 110), TASKS_DURATION=(40, 300) are not based on data analysis
  - If listening patterns change (e.g., users skip more during showers), thresholds become invalid
  - Heuristic rules (SHOWER_HOURS, GYM_HOURS) are timezone-aware (America/Bogota hardcoded) but user may move
  - MIN_CONFIDENCE=0.4 is arbitrary; no ablation study documented
- Safe modification:
  - Any change to duration gates requires rerunning label_activities on full history
  - Update inline comments with rationale and data that informed each threshold
  - Consider exporting thresholds to config file for easier A/B testing
- Test coverage: `tests/test_label_activities.py:1-155` (good, but tests use same hardcoded values)

**Streaming App Reruns Reload All Data:**
- Files: `dashboard/app.py:115-164`
- Why fragile:
  - Every Streamlit interaction (button click, date picker change) triggers a full rerun of app.py
  - Cache decorators prevent re-querying, but all code between queries executes again
  - Risk: If a query function has side effects (logging, API calls), they repeat
  - Risk: If cache is cleared, page becomes slow until cache repopulates (3 hours)
- Safe modification:
  - Keep query functions pure (no side effects)
  - Avoid adding state-altering code inside cached functions
  - Use `@st.cache_resource` only for stateful objects (database engine)
- Test coverage: No automated tests for Streamlit rerun behavior (manual only)

**Concurrent Ingestion Could Cause Data Inconsistency:**
- Files: All ingestion scripts (ingest_plays.py, ingest_audio_features.py, ingest_artists.py)
- Why fragile:
  - Each script uses `ON CONFLICT DO NOTHING` assuming single-instance execution
  - If two processes run simultaneously, they both check "is this track in raw_plays?" and both insert (second is ignored)
  - If `run_pipeline.py` is triggered twice concurrently, sessions might be built from incomplete play data
  - No distributed lock or row-level locking prevents race conditions
- Safe modification:
  - Document strict requirement: only one pipeline instance at a time
  - Add concurrency guard in CI (GitHub Actions `concurrency: group: spotify-pipeline`)
  - If multi-instance ever needed, add advisory locks or sequence IDs
- Test coverage: `tests/test_run_pipeline.py` doesn't test concurrent execution

## Scaling Limits

**Supabase Free Tier Limits:**
- Current capacity: Free tier allows 500 MB storage, 2 CPU shared, connection pooling on 6543
- Limit: At ~100 bytes per play record, 500 MB holds ~5M plays. Current project unknown size, but likely <100k
- Scaling path:
  - Monitor storage: `SELECT pg_size_pretty(pg_database_size('postgres'));` in Supabase console
  - Consider archive strategy: move plays >1 year old to separate partition or backup before hitting limit
  - Upgrade to Pro tier ($25/mo) for 8 GB storage, better compute

**Streamlit Cloud Memory Constraints:**
- Current: App runs in shared container with 256 MB RAM limit
- Limit: Loading millions of rows into memory (e.g., all plays, all sessions) will crash app
- Scaling path:
  - Add pagination/sampling to Streamlit queries
  - Use `@st.cache_data` conservatively; profile memory usage
  - Consider self-hosting on minimal VPS (AWS Free Tier, Heroku) if memory becomes issue

**Dashboard Query Latency with Large Tables:**
- Current: No query optimization (no indexes mentioned in schema)
- Limit: As raw_plays table grows past 1M rows, aggregation queries slow down
- Scaling path:
  - Add database indexes: `CREATE INDEX ON raw_plays(played_at)`, `CREATE INDEX ON sessions(start_time)`
  - Add materialized views for expensive aggregations (top tracks, plays by hour)
  - Consider time-series database (InfluxDB, TimescaleDB) if analytics queries dominate

## Dependencies at Risk

**Supabase Dependency on Spotify API Availability:**
- Risk: If Spotify API goes down or restricts access further, entire pipeline blocks (no fallback data source)
- Impact: No new plays ingested; dashboard shows stale data; no active monitoring
- Migration plan:
  - Add fallback: cache recently fetched data locally and use on API outage
  - Add monitoring: alert if `ingest_plays` produces 0 new rows for 3 consecutive runs
  - Document data freshness SLA (e.g., "data is 24 hours stale if Spotify is down")

**Spotipy Library Version Pinning:**
- Risk: `spotipy==2.24.0` pinned but may become deprecated if Spotipy major version changes
- Impact: Security bugs in older version may not be patched; new Spotify API features unavailable
- Monitoring: Check `pip list --outdated` monthly; test upgrades in separate branch before merging

**PostgreSQL / psycopg2 Version Alignment:**
- Risk: Supabase may upgrade PostgreSQL server version; `psycopg2==2.9.10` may have compatibility issues
- Impact: Connection failures or subtle SQL dialect incompatibilities
- Mitigation: Supabase manages server upgrades; psycopg2 is backward-compatible within major versions
- Check: Monitor Supabase notifications for planned server upgrades

## Test Coverage Gaps

**No Tests for Streaming Dashboard Behavior:**
- What's not tested: Streamlit reruns, cache invalidation, user interactions (date picker, sidebar state)
- Files: `dashboard/app.py:1-466`
- Risk: UI bugs (layout shifts, incorrect data shown for selected date) go unnoticed; cache races hard to debug
- Priority: Medium (UI regressions are visible but annoying; data errors are worse)
- Approach: Add Streamlit testing library (`pytest-streamlit` or similar) for basic rerun scenarios

**No Tests for Pipeline Fault Tolerance:**
- What's not tested: Behavior if Spotify API returns partial data, malformed responses, or timeouts
- Files: `ingestion/ingest_plays.py:58-83`, `ingestion/ingest_audio_features.py:101-157`, `ingestion/ingest_artists.py:96-136`
- Risk: Real API errors (connection timeouts, partial responses) may cause silent data corruption or crashes
- Priority: High (impacts data integrity)
- Approach: Add integration tests with mocked Spotify API returning edge cases (empty items[], null fields, 503 errors)

**No Tests for Concurrent Execution:**
- What's not tested: Multiple pipeline runs triggered simultaneously
- Files: All ingestion and transformation scripts
- Risk: Race conditions on upserts; inconsistent session IDs; duplicate data
- Priority: High (if CI ever runs multiple jobs)
- Approach: Add subprocess-based concurrency test that spawns two pipeline instances and verifies idempotency

**No Tests for Large Data Volumes:**
- What's not tested: Performance and correctness with 1M+ plays, 100k+ sessions
- Files: `transformation/build_sessions.py:70-127`, `transformation/compute_features.py:74-98`, `transformation/label_activities.py:150-250`
- Risk: Memory exhaustion, slow queries, or logic errors only manifest at scale
- Priority: Medium (can defer until dataset grows)
- Approach: Generate 500k synthetic plays and run full pipeline; measure memory and runtime

**Dashboard Cache Invalidation Not Tested:**
- What's not tested: TTL behavior, manual cache clear, race conditions if ingestion completes during cache window
- Files: `dashboard/app.py:115-164`
- Risk: Users see stale data; adding refresh button might not clear all cached functions
- Priority: Low (users see stale data at worst, not broken data)
- Approach: Add unit tests for cache decorator behavior; verify all query functions are decorated

---

*Concerns audit: 2026-04-15*
