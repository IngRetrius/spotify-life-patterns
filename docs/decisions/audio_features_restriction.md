# Decision: Audio Features unavailable — strategy adjustment

## What happened

When running `ingest_audio_features.py`, the `/audio-features` endpoint returned
**HTTP 403** — access denied, not just deprecated.

```
GET /v1/audio-features/?ids=...  →  403 Forbidden
```

## Why this happens

Spotify segmented its endpoints into access tiers. Since 2024,
`/audio-features` requires manual approval ("Extended Access") that Spotify
grants only to verified commercial applications. New apps in Development
Mode receive 403 directly.

This is independent of the "deprecated" label — the endpoint was deprecated
AND restricted at the same time.

## Impact on the design

**Features we lose:**
- tempo (BPM)
- energy, danceability, valence
- acousticness, instrumentalness
- loudness, speechiness, liveness

**Features we keep** (no dependency on that endpoint):

| Feature | Source | How it is computed |
|---|---|---|
| `duration_minutes` | raw_plays | sum(duration_ms) / 60000 per session |
| `n_tracks` | raw_plays | count of tracks per session |
| `n_skips` | raw_plays | tracks where listened < 50% of duration_ms |
| `hour_of_day` | raw_plays.played_at | EXTRACT(hour FROM played_at) |
| `day_of_week` | raw_plays.played_at | EXTRACT(dow FROM played_at) |
| `dominant_genre` | raw_artists.genres | mode of genres in the session |

## Adjustment to the heuristic rules

Activities are inferred with the features still available:

```
SHOWER
  - duration_minutes BETWEEN 5 AND 15
  - n_skips < 2  (cannot interact with the phone)
  - hour_of_day IN (6,7,8,9) OR hour_of_day IN (21,22,23)

GYM
  - duration_minutes BETWEEN 45 AND 90
  - n_skips < 5  (continuous music)
  - Recurring pattern: same day_of_week, same hour_of_day

WORK / FOCUS
  - duration_minutes > 90
  - hour_of_day BETWEEN 8 AND 18
  - day_of_week BETWEEN 0 AND 4  (Monday to Friday)

REST / NIGHT
  - hour_of_day BETWEEN 22 AND 24 OR hour_of_day IN (0, 1)
  - low n_skips (passive listening)

MOTORCYCLE
  - Continuous session (gap between tracks < 5 min)
  - n_skips = 0  (cannot interact)
  - duration_minutes variable
```

## Why this matters for the portfolio

Documenting that the endpoint was restricted and that the project adapted to
it demonstrates the ability to respond to API changes — something very common
in real Data Engineering work. A pipeline that depends on a single endpoint
with no error handling is fragile; this project handles it with graceful
degradation (NULL storage + adjusted rules).

## Status in raw_audio_features

The 50 tracks in raw_plays were recorded in raw_audio_features with every
field NULL (except track_id). This prevents the pipeline from retrying to
fetch features on every future run, wasting API calls that would fail anyway.
