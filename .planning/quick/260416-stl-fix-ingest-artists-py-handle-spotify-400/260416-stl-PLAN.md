---
phase: quick-260416-stl
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - ingestion/ingest_artists.py
autonomous: true
requirements:
  - QUICK-01
must_haves:
  truths:
    - "Pipeline step [3/6] Ingest artists no longer aborts when raw_plays contains a non-standard artist_id (e.g. local files, malformed entries)"
    - "Artist IDs that don't match ^[0-9A-Za-z]{22}$ are routed to the fallback path (name from raw_plays, genres/popularity NULL) without calling /artists"
    - "If a 400 from Spotify slips through (e.g. ID looks valid but is rejected), the batch falls back to raw_plays names instead of raising and killing the pipeline"
    - "Existing 429 (rate-limit with Retry-After) and 403 (endpoint restricted) handling remains unchanged in behavior"
    - "All artists from every batch (valid + invalid) end up upserted into raw_artists in a single pipeline run"
  artifacts:
    - path: "ingestion/ingest_artists.py"
      provides: "ID pre-validation + broadened 400/403 fallback"
      contains: "SPOTIFY_ID_RE"
  key_links:
    - from: "ingestion/ingest_artists.py::run"
      to: "ingestion/ingest_artists.py::fetch_artists"
      via: "pre-filtered valid_ids passed to fetch_artists; invalid_ids upserted directly as fallback rows"
      pattern: "SPOTIFY_ID_RE\\.match"
    - from: "ingestion/ingest_artists.py::fetch_artists"
      to: "fallback branch"
      via: "SpotifyException handler covering both 400 and 403"
      pattern: "e\\.http_status in \\(400, 403\\)"
---

<objective>
Fix `ingestion/ingest_artists.py` so a single invalid `artist_id` (local files, malformed entries from `raw_plays`) can no longer abort the pipeline at step [3/6].

Purpose: Restore green pipeline runs. Current failure: `ERROR: http status: 400, code: -1 - Unsupported URL / URI.` kills the whole batch because `fetch_artists` only special-cases 429 and 403.

Output: Updated `ingest_artists.py` that (a) pre-filters IDs to the Spotify base62 22-char shape before calling `/artists`, and (b) treats 400 exactly like 403 — fall back to names from `raw_plays` with `genres`/`popularity = NULL`.
</objective>

<execution_context>
@$HOME/.claude-trabajo-trabajo/get-shit-done/workflows/execute-plan.md
@$HOME/.claude-trabajo-trabajo/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@.planning/STATE.md
@ingestion/ingest_artists.py

<interfaces>
<!-- Key shapes the executor needs. No codebase exploration required. -->

Spotify artist ID format (from Spotify Web API docs):
- 22 characters
- base62 alphabet: [0-9A-Za-z]
- Regex: `^[0-9A-Za-z]{22}$`
- Anything else (local-file URIs like `spotify:local:...`, empty strings, truncated IDs, etc.) is invalid and will 400 against `/v1/artists`.

Existing function signature (unchanged):
```python
def fetch_artists(sp: spotipy.Spotify, artist_ids: list[str], fallback_names: dict) -> list[dict]:
    # returns list of {"artist_id", "name", "genres", "popularity"}
```

Fallback row shape (already used by the 403 branch, reuse verbatim):
```python
{"artist_id": aid,
 "name": fallback_names.get(aid, aid),
 "genres": None,
 "popularity": None}
```

Upsert SQL is idempotent (`ON CONFLICT (artist_id) DO NOTHING`) — safe to upsert fallback rows.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="false">
  <name>Task 1: Pre-filter invalid artist_ids and broaden 400/403 fallback</name>
  <files>ingestion/ingest_artists.py</files>
  <behavior>
    - Module exposes a module-level `SPOTIFY_ID_RE = re.compile(r"^[0-9A-Za-z]{22}$")` (add `import re` near the other stdlib imports).
    - `run()` splits `artist_ids` into `valid_ids` (match `SPOTIFY_ID_RE`) and `invalid_ids` (everything else) BEFORE entering the batch loop.
    - When `invalid_ids` is non-empty: print a single summary line (e.g. `"N artist_ids invalidos (no base62-22). Guardando nombre desde raw_plays."`), build fallback rows using the same shape as the existing 403 branch, upsert them, commit, and add their count to `total_inserted`. Do NOT send them to `/artists`.
    - The batch loop iterates over `valid_ids` only (not the original `artist_ids`).
    - `fetch_artists()` SpotifyException handler: change `elif e.http_status == 403:` to `elif e.http_status in (400, 403):`. Update the print to cover both: `f"  Endpoint /artists rechazo el batch (HTTP {e.http_status}). Guardando nombres desde raw_plays."`. Fallback body is unchanged.
    - Existing 429 branch (Retry-After + backoff) is preserved verbatim.
    - Final `"Resumen: N artistas insertados en raw_artists."` line still prints and reflects valid + invalid + fallback rows combined.
  </behavior>
  <action>
    1. Add `import re` alongside the other stdlib imports (`sys`, `time`, `os`). Keep import ordering: stdlib first, then third-party, then local — per CLAUDE.md conventions.
    2. Add module-level constant after the existing constants block:
       ```python
       SPOTIFY_ID_RE = re.compile(r"^[0-9A-Za-z]{22}$")
       ```
    3. In `fetch_artists()`, change the 403 branch to also catch 400:
       ```python
       elif e.http_status in (400, 403):
           # 403: endpoint restringido (cambios API Spotify 2024).
           # 400: algun ID del batch es invalido (p.ej. local file slipped past validation).
           # En ambos casos, fallback: nombre desde raw_plays, genres/popularity NULL.
           print(f"  Endpoint /artists rechazo el batch (HTTP {e.http_status}). Guardando nombres desde raw_plays.")
           return [{"artist_id": aid,
                    "name": fallback_names.get(aid, aid),
                    "genres": None,
                    "popularity": None}
                   for aid in artist_ids]
       ```
       (Replace the existing 403-only block; do NOT duplicate.)
    4. In `run()`, after building `fallback_names` and `artist_ids`, split the list:
       ```python
       valid_ids   = [aid for aid in artist_ids if SPOTIFY_ID_RE.match(aid)]
       invalid_ids = [aid for aid in artist_ids if not SPOTIFY_ID_RE.match(aid)]

       if invalid_ids:
           print(f"{len(invalid_ids)} artist_ids invalidos (no base62-22). Guardando nombre desde raw_plays.")
           fallback_rows = [{"artist_id": aid,
                             "name": fallback_names.get(aid, aid),
                             "genres": None,
                             "popularity": None}
                            for aid in invalid_ids]
           inserted = upsert_artists(cursor, fallback_rows)
           conn.commit()
           total_inserted += inserted
       ```
    5. Change the batch log line and loop source from `artist_ids` to `valid_ids`:
       ```python
       print(f"{len(valid_ids)} artistas sin metadata (validos). Procesando en batches de {ARTISTS_BATCH}...")

       for i, batch in enumerate(chunk(valid_ids, ARTISTS_BATCH)):
           ...
       ```
       Keep the rest of the loop body (batch fetch, upsert, commit, sample genres print) unchanged.
    6. Do NOT touch `get_artists_without_metadata`, `UPSERT_ARTISTS_SQL`, `upsert_artists`, `chunk`, or `get_spotify_client` — no DB schema changes, no signature changes.
    7. Keep all existing prints (section headers, per-batch logging, final summary) — project conventions rely on print-based observability.
  </action>
  <verify>
    <automated>python -c "import ast,re; src=open('ingestion/ingest_artists.py',encoding='utf-8').read(); ast.parse(src); assert 'SPOTIFY_ID_RE' in src and re.search(r'e\\.http_status in \\(400, 403\\)', src) and 'valid_ids' in src and 'invalid_ids' in src, 'missing expected edits'; print('OK')"</automated>
  </verify>
  <done>
    - `python -c "import ingestion.ingest_artists"` imports cleanly (no syntax / import errors).
    - `SPOTIFY_ID_RE` is defined at module level and used in `run()` to split `valid_ids` / `invalid_ids`.
    - `fetch_artists` handler catches both 400 and 403 with identical fallback behavior.
    - Existing 429 handler is unchanged.
    - `get_artists_without_metadata`, `upsert_artists`, `UPSERT_ARTISTS_SQL`, and `chunk` are untouched.
    - Manual smoke (next pipeline run): step [3/6] no longer aborts on batches containing non-base62 IDs; fallback rows land in `raw_artists` with `genres=NULL, popularity=NULL`.
  </done>
</task>

</tasks>

<verification>
- `python -m py_compile ingestion/ingest_artists.py` exits 0.
- `python -c "import ingestion.ingest_artists as m; assert m.SPOTIFY_ID_RE.match('4Z8W4fKeB5YxbusRsdQVPb'); assert not m.SPOTIFY_ID_RE.match('spotify:local:foo'); assert not m.SPOTIFY_ID_RE.match('short'); print('OK')"` prints `OK`.
- Next real pipeline run (or `python ingestion/ingest_artists.py` against prod creds) completes step [3/6] without `ERROR: http status: 400`.
</verification>

<success_criteria>
- Pipeline step [3/6] Ingest artists completes end-to-end when `raw_plays` contains invalid `artist_id` values.
- Invalid IDs (non base62-22) are upserted with `name` from `raw_plays` and `genres/popularity = NULL`, never sent to `/artists`.
- A 400 from Spotify no longer raises out of `fetch_artists`; it falls back like 403.
- No changes to DB schema, no changes to other pipeline steps, no changes to the 429 retry logic.
- Code style matches CLAUDE.md: snake_case, type hints preserved, print-based logging, stdlib imports grouped with existing ones.
</success_criteria>

<output>
After completion, create `.planning/quick/260416-stl-fix-ingest-artists-py-handle-spotify-400/260416-stl-SUMMARY.md`
</output>
