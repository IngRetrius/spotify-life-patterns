# Transformation Layer — Design Decisions

## The three steps and why that order

```
build_sessions.py → compute_features.py → label_activities.py
```

Each step depends on the previous one and has a single responsibility.
They cannot be reordered because each one reads what the previous one wrote.

---

## 1. build_sessions.py — session construction

### Grouping algorithm

```
plays ordered by played_at:
  A (3:00) → B (3:04) → C (3:09) → [gap 45 min] → D (3:54) → ...

gap between C and D = 45 min > 30 min = new session

Session 1: A, B, C
Session 2: D, ...
```

### Why session_id is deterministic (uuid5)

`session_id = uuid5(NAMESPACE_URL, start_time.isoformat())`

With a random UUID: every time you rebuild sessions, the IDs change.
References from `session_features` and `activity_labels` end up orphaned.

With a deterministic UUID: the same start_time always produces the same ID.
You can rebuild sessions N times and the upsert remains safe.

### Computing end_time

`end_time = played_at of the last track + its duration_ms`

It is not simply the `played_at` of the last track, because that timestamp
marks *when that song started*. If the session ends with a 3-minute track,
the real end of the session is 3 minutes later.

### Why pandas and not pure SQL

Gap-based grouping logic requires comparing each row to the previous one.
In SQL that needs window functions and self-joins that are verbose.
In pandas: `df["gap"] = df["played_at"] - df["played_at"].shift(1)` — one line.

For small datasets (< millions of rows), in-memory pandas is sufficient.
In a Spark- or dbt-based architecture this logic would translate to SQL
with `LAG()`.

---

## 2. compute_features.py — features per session

### Skip detection

```
A track is a "skip" if:
  played_at[i+1] - played_at[i] < duration_ms[i] * 0.5
```

That is: if the next song started before half of the current one had played.

We cannot directly know whether the user pressed "next" — we only see
timestamps. This proxy is an approximation: it does not capture long pauses
or slow listening.

### merge_asof to assign plays to sessions

Instead of a range-condition JOIN (slow on large datasets), we use
`pd.merge_asof`: an ordered merge that for each play finds the session
with `start_time <= played_at`. Afterwards we filter out any plays that
exceed `end_time`.

### Audio features as NULL

With the endpoint restricted, `avg_bpm`, `avg_energy`, etc. are NULL.
They are still stored in `session_features` for the day the endpoint is
available again or is replaced with an alternative source.

---

## 3. label_activities.py — heuristic labeling

### Why rules and not ML from the start

1. There is not enough data to train on (50 plays = 4 sessions)
2. Rules are auditable and explainable — you know exactly why a session
   was labeled as "gym"
3. The rules generate the training dataset for ML in phase 2

### Why 3 activities (not 5)

The original design had 5 rules: shower, gym, motorcycle, work, rest.
The problem: without audio features, motorcycle and work are
indistinguishable by duration and hour alone. A 103-minute session at 3am
was being labeled as "motorcycle" when it was clearly late-night studying.

Decision: reduce to 3 activities with clear, mutually exclusive temporal
signals:

| Activity | Dominant signal       | Hour differentiator             |
|----------|-----------------------|---------------------------------|
| shower   | Very short, 5–20 min  | Morning (6–10h) or night (20–23h) |
| gym      | Duration 35–110 min   | Day/afternoon (5–10h or 16–22h) |
| tasks    | Duration > 40 min     | Late night (0–5h or 22–23h)     |

The hour bonus is the key discriminator: gym and tasks can last the same
(60–90 min), but gym does not happen at 3am.

### Confidence score system

Each rule adds points per condition satisfied (max total = 1.0).
The rule with the highest score wins. If none exceeds 0.4 → "unknown".

```python
SHOWER_HOURS      = set(range(6, 11))  | set(range(20, 24))   # 6-10h and 20-23h
GYM_HOURS         = set(range(5, 11))  | set(range(16, 23))   # 5-10h and 16-22h
NIGHT_STUDY_HOURS = set(range(22, 24)) | set(range(0, 6))     # 22-23h and 0-5h

def rule_shower(row):   # max 0.5 + 0.3 + 0.2 = 1.0
    if 5 <= duration <= 20:        score += 0.5  # primary condition
    if n_skips == 0:               score += 0.3  # cannot touch the phone
    if hour in SHOWER_HOURS:       score += 0.2  # typical grooming hours

def rule_gym(row):      # max 0.4 + 0.3 + 0.3 = 1.0
    if 35 <= duration <= 110:      score += 0.4  # typical workout duration
    if n_skips <= 2:               score += 0.3  # continuous music
    if hour in GYM_HOURS:          score += 0.3  # 5-10am or 4-10pm

def rule_tasks(row):    # max 0.5 + 0.2 + 0.3 = 1.0
    if duration > 40:              score += 0.5  # long session
    if n_skips <= 5:               score += 0.2  # background music
    if hour in NIGHT_STUDY_HOURS:  score += 0.3  # late night = studying
```

Results for the current 4 sessions:

| Session      | Dur    | Hour | Skips | Label   | Score |
|--------------|--------|------|-------|---------|-------|
| 38e0b333...  | 103.5m | 3h   | 0     | tasks   | 1.00  |
| 74ca3bf1...  | 14.5m  | 17h  | 0     | shower  | 0.80  |
| 44158cee...  | 62.3m  | 20h  | 2     | gym     | 1.00  |
| 83e34a9d...  | 2.6m   | 23h  | 0     | shower  | 0.50  |

The score is not a statistical probability — it is a measure of how many
conditions are satisfied. With more data it can be replaced with a classifier
that produces real probabilities.

---

## The orchestrator run_pipeline.py

Runs the 6 steps in order. Key features:

- `--from N`: start from step N. Useful for re-running only the
  transformation without calling the Spotify API again.
- If a step fails, the pipeline stops — no partial results are written.
- Measures the time of each step: useful for identifying bottlenecks.

```bash
python scripts/run_pipeline.py          # full pipeline
python scripts/run_pipeline.py --from 4 # transformation only
```

---

## Full data flow

```
Spotify API
    ↓ ingest_plays.py
raw_plays (50 rows)
    ↓ ingest_audio_features.py
raw_audio_features (50 rows, features NULL due to API restriction)
    ↓ ingest_artists.py
raw_artists (33 rows, genres NULL due to API restriction)
    ↓ build_sessions.py
sessions (4 sessions grouped by gap < 30 min)
    ↓ compute_features.py
session_features (4 records: n_skips computed, audio features NULL)
    ↓ label_activities.py
activity_labels (4 labels: shower/gym/tasks + confidence)
```
