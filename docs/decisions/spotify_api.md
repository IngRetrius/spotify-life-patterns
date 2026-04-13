# Spotify Web API — Findings and Decisions

> Documentation of what we learned about the API before writing the ingestion code.
> Source: https://developer.spotify.com/documentation/web-api

---

## Endpoints we use and their limits

### 1. Recently Played Tracks
```
GET https://api.spotify.com/v1/me/player/recently-played
```

| Field | Value |
|---|---|
| Required scope | `user-read-recently-played` |
| Max per request | 50 tracks |
| Pagination | Cursor-based (before/after in Unix ms), NOT offset |
| Not supported | Podcast episodes |

**Useful parameters:**
- `limit` — how many tracks to fetch (1–50)
- `before` — ms timestamp: fetch tracks played BEFORE that moment
- `after` — ms timestamp: fetch tracks played AFTER that moment
- `before` and `after` are mutually exclusive

**Relevant response fields per item:**
```json
{
  "track": {
    "id": "...",
    "name": "...",
    "duration_ms": 210000,
    "artists": [{ "id": "...", "name": "..." }],
    "album": { "name": "..." }
  },
  "played_at": "2024-01-15T14:30:00Z"
}
```

---

### 2. Audio Features (DEPRECATED)
```
GET https://api.spotify.com/v1/audio-features?ids={ids}
```

| Field | Value |
|---|---|
| Required scope | None |
| Max IDs per request | 100 |
| **Status** | **DEPRECATED** — may be removed by Spotify |

**Fields returned:**
| Field | Type | Description |
|---|---|---|
| `tempo` | float | Estimated BPM |
| `energy` | float 0-1 | Perceived intensity |
| `danceability` | float 0-1 | Suitability for dancing |
| `valence` | float 0-1 | Emotional positivity |
| `acousticness` | float 0-1 | Acoustic presence |
| `instrumentalness` | float 0-1 | Absence of vocals |
| `loudness` | float (dB) | Average volume |
| `speechiness` | float 0-1 | Spoken words |
| `liveness` | float 0-1 | Probability of being live |
| `key` | int -1 to 11 | Musical key |
| `mode` | int 0/1 | 0=minor, 1=major |
| `time_signature` | int 3-7 | Time signature |

**Decision taken:** implement with try/except and store features as NULL if the
endpoint fails. The pipeline must not break if Spotify removes this endpoint.

---

### 3. Get Several Artists (genres DEPRECATED)
```
GET https://api.spotify.com/v1/artists?ids={ids}
```

| Field | Value |
|---|---|
| Required scope | None |
| Max IDs per request | 50 |

**Fields returned:**
- `id`, `name` — stable
- `genres` — array of strings. **DEPRECATED**
- `popularity` — integer 0-100. **DEPRECATED**
- `followers` — **DEPRECATED**

**Decision taken:** store genres as optional data. The `dominant_genre` logic
in `session_features` works when genres are present but does not fail when the
array is empty. Future phases can replace this with a custom classifier based
on artist name or playlist.

---

## Authentication — Authorization Code Flow

```
User → Your app → Spotify /authorize → User approves → callback with code
→ Your app exchanges code for (access_token + refresh_token)
→ access_token lasts 1 hour → refresh_token renews it without user intervention
```

**Why Authorization Code and not Client Credentials?**

Client Credentials authenticates the *app*, not the *user*. The
`recently-played` endpoint needs to know who the user is. Only Authorization
Code grants access to user endpoints (those with `user-read-*` scopes).

**spotipy handles all of this automatically:**
- Stores tokens in `.cache` (already in `.gitignore`)
- Refreshes the `access_token` with the `refresh_token` when it expires
- The first time it opens the browser so the user can authorize

---

## Rate Limits

**How it works:**
- Rolling **30-second** window
- In development mode (new apps): lower unpublished limit
- When exceeded: `HTTP 429` with header `Retry-After: N` (seconds to wait)

**Strategy implemented in the pipeline:**
```python
# If the API returns 429, wait exactly what Retry-After says
# If the header is missing, use exponential backoff: 1s, 2s, 4s, 8s...
```

**How to minimize calls (Spotify best practices):**
1. Use batch endpoints: `/audio-features?ids=id1,id2,...,id100`
   instead of calling once per track
2. Do not re-fetch data we already have: if `track_id` is already in
   `raw_audio_features`, do not request its features again
3. The ingestion pipeline runs every 6 hours, not in real time

---

## Summary of batch limits for the pipeline

| What we request | Endpoint | IDs per call | Strategy |
|---|---|---|---|
| History | `/me/player/recently-played` | 50 tracks | Cursor pagination with `before` |
| Audio features | `/audio-features` | 100 IDs | Group in chunks of 100 |
| Artists | `/artists` | 50 IDs | Group in chunks of 50 |

---

## Impact of deprecations on the design

Two deprecations affect our schema:

| Deprecation | Affects | Decision |
|---|---|---|
| `/audio-features` endpoint | `raw_audio_features` | Insert NULL on failure. Pipeline does not break. |
| `genres` and `popularity` in `/artists` | `dominant_genre` in `session_features` | Treat as optional. If empty, `dominant_genre = NULL`. |

**Why this matters for the portfolio:**
Documenting that we were aware of the deprecations and designed around them
demonstrates engineering maturity. A pipeline that breaks when the API changes
is a poorly designed pipeline.

---

## Scope configured in the project

```python
# config/settings.py
SPOTIFY_SCOPE = "user-read-recently-played"
```

This is the only scope needed. We do not request more permissions than required
(principle of least privilege).
