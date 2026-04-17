---
phase: quick-260416-stl
plan: 01
subsystem: ingestion
tags: [bugfix, spotify-api, resilience]
requires: []
provides:
  - ID pre-validation gate before /artists batch call
  - Unified 400/403 fallback in fetch_artists
affects:
  - ingestion/ingest_artists.py
tech_stack:
  added: []
  patterns:
    - "Input validation via regex guard before third-party API call"
    - "Broadened exception handler to cover correlated failure modes (400 + 403)"
key_files:
  created: []
  modified:
    - ingestion/ingest_artists.py
decisions:
  - "Handle 400 identically to 403: name-only fallback from raw_plays; avoids pipeline abort when a single invalid ID appears in a batch"
  - "Pre-filter using SPOTIFY_ID_RE (^[0-9A-Za-z]{22}$) so invalid IDs never hit /artists — cheaper and keeps API logs clean"
metrics:
  duration: "~1m"
  completed: 2026-04-17
---

# Quick 260416-stl Plan 01: Fix `ingest_artists.py` — handle Spotify 400 Summary

**One-liner:** Pre-validate artist_ids against base62-22 regex and broaden the SpotifyException fallback to (400, 403) so a single invalid ID (local file URIs, malformed entries in `raw_plays`) no longer aborts pipeline step [3/6].

## What Changed

- Added `import re` (grouped with stdlib imports) and module-level `SPOTIFY_ID_RE = re.compile(r"^[0-9A-Za-z]{22}$")`.
- In `run()`, after building `fallback_names`/`artist_ids`, split into `valid_ids` and `invalid_ids`. When `invalid_ids` is non-empty, print a summary line, build fallback rows (shape identical to the 403 branch), upsert them, commit, and add the count to `total_inserted`. The batch loop now iterates over `valid_ids`.
- In `fetch_artists()`, changed the `elif e.http_status == 403` branch to `elif e.http_status in (400, 403)` with a unified print: `"Endpoint /artists rechazo el batch (HTTP {e.http_status}). Guardando nombres desde raw_plays."` Fallback body unchanged.
- 429 retry branch preserved verbatim.
- No changes to `get_artists_without_metadata`, `UPSERT_ARTISTS_SQL`, `upsert_artists`, `chunk`, or `get_spotify_client`.

## Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Pre-filter invalid artist_ids and broaden 400/403 fallback | e2d3dcc | ingestion/ingest_artists.py |

## Verification

Automated (from plan `<verify>`):

```
$ python -c "import ast,re; src=open('ingestion/ingest_artists.py',encoding='utf-8').read(); ast.parse(src); assert 'SPOTIFY_ID_RE' in src and re.search(r'e\\.http_status in \\(400, 403\\)', src) and 'valid_ids' in src and 'invalid_ids' in src, 'missing expected edits'; print('OK')"
OK

$ python -m py_compile ingestion/ingest_artists.py
# exit 0

$ python -c "import ingestion.ingest_artists as m; assert m.SPOTIFY_ID_RE.match('4Z8W4fKeB5YxbusRsdQVPb'); assert not m.SPOTIFY_ID_RE.match('spotify:local:foo'); assert not m.SPOTIFY_ID_RE.match('short'); print('OK')"
OK
```

All three checks pass. Real pipeline smoke test happens on next scheduled GitHub Actions run (or manual `python ingestion/ingest_artists.py`).

## Deviations from Plan

None — plan executed exactly as written.

## Success Criteria

- [x] Pipeline step [3/6] no longer aborts on batches containing non-base62 IDs (invalid IDs routed to fallback before `/artists`).
- [x] Invalid IDs upserted with `name` from `raw_plays` and `genres/popularity = NULL`, never sent to `/artists`.
- [x] 400 from Spotify now falls back like 403 inside `fetch_artists` — no raise.
- [x] No DB schema changes, no other pipeline steps touched, 429 retry logic untouched.
- [x] Code style matches CLAUDE.md conventions (snake_case, type hints preserved, print-based logging, stdlib imports grouped).

## Self-Check: PASSED

- FOUND: ingestion/ingest_artists.py (modified)
- FOUND commit: e2d3dcc
