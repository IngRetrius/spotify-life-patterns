# Design Decisions — Database

> This document records the reasoning behind every schema decision.
> It is the answer to "why did you design the database this way?" in an interview.

---

## The most important decision: two separate layers

The schema has 6 tables split into two groups with completely different purposes:

```
RAW LAYER (Bronze)        ANALYTICS LAYER (Silver/Gold)
─────────────────         ─────────────────────────────
raw_plays                 sessions
raw_audio_features        session_features
raw_artists               activity_labels
```

**Raw layer** = data exactly as it arrived from the Spotify API. Never modified.

**Analytics layer** = data we compute. Can be dropped and recomputed at any time.

### Why this separation matters

Imagine that in three months you change how a "session" is defined (e.g. from
a 30-minute gap to a 20-minute gap). With this separation:

- Drop `sessions`, `session_features`, `activity_labels`
- Re-run the transformation
- The raw data stays intact in `raw_plays`

Without this separation, you would lose the original Spotify data forever.

This pattern has a name: **Medallion Architecture** (Bronze → Silver → Gold).
It is the industry standard — used by Databricks, Snowflake, dbt.

---

## Why `sessions`, `session_features` and `activity_labels` are three tables instead of one

You could have put everything in a single `sessions` table with 20 columns.
That was rejected because each table has a **different reason to change**:

| Table | Answers | Changes when |
|---|---|---|
| `sessions` | When did this session occur? | The gap definition changes (30 min) |
| `session_features` | How did it sound musically? | The audio features we use change |
| `activity_labels` | What activity was it? | The rules or the ML model change |

This is the **Single Responsibility Principle** applied to tables.

Concrete benefit: when the heuristic rules are replaced by an ML model in phase 2,
only `activity_labels` changes. Sessions and their features stay untouched.

---

## `UNIQUE (track_id, played_at)` — pipeline idempotency

```sql
UNIQUE (track_id, played_at)
```

The cron runs every 6 hours. Spotify returns the last 50 tracks. A song played
at 5pm can appear both in the 4pm run and in the 6pm run.

Without this constraint: the same play would be inserted twice, sessions would
be duplicated, and dashboard metrics would be wrong.

With this constraint: the insert becomes an **upsert** — inserts if it does not
exist, ignores if it does. You can run the pipeline 100 times over the same
data and the result is always the same.

**The property this guarantees: idempotency.**

> In Data Engineering, an idempotent pipeline is one where running it N times
> produces exactly the same result as running it once. It is a fundamental
> property for building reliable pipelines.

---

## `TIMESTAMPTZ` and not `TIMESTAMP`

```sql
played_at TIMESTAMPTZ NOT NULL
```

| Type | Behavior |
|---|---|
| `TIMESTAMP` | Stores the time without a timezone. What you insert is what you get back. |
| `TIMESTAMPTZ` | Stores in UTC internally. Converts to the client timezone on read. |

Spotify reports `played_at` in UTC. Colombia is UTC-5. Using `TIMESTAMP` and
mixing timestamps from different sources would leave your hour-of-day analysis
off by 5 hours.

**General rule:** always store UTC in the database. Convert to the user's
timezone only at the presentation layer (the Streamlit dashboard).

---

## `TEXT[]` for genres — native Postgres arrays

```sql
genres TEXT[]   -- example: ["reggaeton", "latin pop", "urbano latino"]
```

An artist has multiple genres in Spotify. The alternatives considered:

| Option | Why rejected |
|---|---|
| `TEXT` with JSON string `'["reggaeton","pop"]'` | Hard to filter. `LIKE '%reggaeton%'` is brittle and slow |
| Separate `artist_genres` table | Overkill — adds a JOIN to every query for a simple relationship |
| `TEXT[]` native array | Filterable, indexable, zero overhead |

With a native array you can write clean queries:
```sql
-- All sessions where the artist is reggaeton
SELECT * FROM raw_artists WHERE 'reggaeton' = ANY(genres);
```

---

## `ON DELETE CASCADE` — referential integrity

```sql
session_id UUID REFERENCES sessions(session_id) ON DELETE CASCADE
```

`session_features` and `activity_labels` have no meaning without their parent
session. If you delete a session (to recompute), `CASCADE` automatically deletes
the associated features and labels.

Without `CASCADE`: you would be left with **orphan rows** — data pointing to a
session that no longer exists. That silently corrupts your analysis because
JOINs return incorrect results without raising any error.

---

## UUIDs vs auto-increment integers

```sql
id UUID DEFAULT gen_random_uuid() PRIMARY KEY
```

| Primary key | How it works |
|---|---|
| `SERIAL` / `BIGSERIAL` | The database generates the ID on INSERT. You do not know the ID before inserting. |
| `UUID` | You can generate the ID in Python before inserting. |

In the transformation pipeline, when you build a session in Python, you need
the `session_id` in order to insert into `sessions` AND `session_features` at
the same time.

With UUID: you generate `session_id = uuid.uuid4()` in Python and use it in
both inserts directly.

With SERIAL: you would INSERT into `sessions`, then SELECT to get the generated
ID, then INSERT into `session_features`. Two database round-trips instead of one.

---

## The indexes — why these and not others

```sql
CREATE INDEX idx_raw_plays_played_at   ON raw_plays (played_at DESC);
CREATE INDEX idx_raw_plays_track_id    ON raw_plays (track_id);
CREATE INDEX idx_sessions_start_time   ON sessions  (start_time DESC);
CREATE INDEX idx_activity_labels_label ON activity_labels (activity_label);
```

Each index exists because there is a frequent query that justifies it:

| Index | Query it accelerates |
|---|---|
| `played_at DESC` | Session construction: order all plays by time |
| `track_id` | JOIN with `raw_audio_features` to enrich each play |
| `start_time DESC` | Dashboard: "sessions this week / last month" |
| `activity_label` | Dashboard: "all gym sessions" |

**Why we did not index everything:** each index has a write-speed cost (the
index is updated on every INSERT). Indexes are only created where the read
pattern justifies them.

---

## Executive summary for interviews

Three principles applied in this design:

1. **Immutability of raw data** (Medallion Architecture)
   API data is never modified. All processing produces new tables.
   Lets you reprocess without losing the original information.

2. **Single Responsibility per table**
   Each table has exactly one reason to change. Makes it possible to evolve
   the pipeline in parts without affecting the rest.

3. **Idempotency through constraints**
   `UNIQUE (track_id, played_at)` makes the pipeline safely re-runnable.
   Reliable pipelines are idempotent by design, not by luck.

> Short interview answer:
> "I separated raw from analytics to keep immutable data and reprocess without
> losing information. Inside analytics I applied Single Responsibility so each
> transformation layer can evolve independently. Uniqueness constraints make
> the pipeline idempotent — I can run it N times with no side effects."
