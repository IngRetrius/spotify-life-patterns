# Phase 1: Timezone Fix - Pattern Map

**Mapped:** 2026-04-15
**Files analyzed:** 3 (1 modified, 1 verified, 1 optional test addition)
**Analogs found:** 3 / 3

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `transformation/build_sessions.py` | transformer + writer | CRUD (upsert) | itself (uncommitted fix already present) | exact — read the live file |
| `scripts/run_pipeline.py` | orchestrator | request-response (sequential steps) | itself — `--from` flag already implemented | exact — verify `from_step` logic |
| `tests/test_build_sessions.py` | test | transform validation | itself — `_plays()` factory + class structure | exact — follow existing class pattern |

---

## Pattern Assignments

### `transformation/build_sessions.py` (transformer + writer, CRUD)

**Status:** Fix already applied in working tree (uncommitted). No code change needed — commit as-is.

**Analog:** itself (current working tree state)

**Imports pattern** (lines 23-34):
```python
import sys
import uuid
import pandas as pd
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.connection import get_connection as get_db_connection

load_dotenv()
```

**Timezone fix core pattern** (lines 113-125):
```python
# Convert to Bogota local time to get the correct hour and weekday.
# start_time is UTC-aware; .tz_convert shifts it to America/Bogota (UTC-5).
start_local = start_time.tz_convert("America/Bogota")

sessions.append({
    "session_id":       make_session_id(start_time),
    "start_time":       start_time.isoformat(),
    "end_time":         end_time.isoformat(),
    "duration_minutes": round(duration_minutes, 2),
    "n_tracks":         len(group),
    "hour_of_day":      start_local.hour,
    "day_of_week":      start_local.dayofweek,   # 0=Mon, 6=Sun
})
```

Note: `make_session_id(start_time)` still receives the original UTC timestamp (line 118) — the deterministic session_id is intentionally based on UTC so existing IDs remain stable across the re-run.

**Upsert pattern with DO UPDATE SET** (lines 132-141):
```python
UPSERT_SESSION_SQL = """
    INSERT INTO sessions
        (session_id, start_time, end_time, duration_minutes, n_tracks, hour_of_day, day_of_week)
    VALUES
        (%(session_id)s, %(start_time)s, %(end_time)s, %(duration_minutes)s,
         %(n_tracks)s, %(hour_of_day)s, %(day_of_week)s)
    ON CONFLICT (session_id) DO UPDATE SET
        hour_of_day = EXCLUDED.hour_of_day,
        day_of_week = EXCLUDED.day_of_week;
"""
```

This is the key correctness mechanism: `DO UPDATE SET` overwrites the stale UTC-based `hour_of_day` and `day_of_week` for any existing session_id on re-run.

**Error handling + transaction pattern** (lines 165-195):
```python
conn = get_db_connection()
conn.autocommit = False
cursor = conn.cursor()

try:
    # ... load, transform, upsert ...
    conn.commit()
    return {"sessions_built": len(sessions), "df_with_sessions": df}

except Exception as e:
    conn.rollback()
    print(f"\nERROR: {e}")
    sys.exit(1)

finally:
    cursor.close()
    conn.close()
```

**execute_batch call** (line 148):
```python
psycopg2.extras.execute_batch(cursor, UPSERT_SESSION_SQL, sessions, page_size=100)
```

---

### `scripts/run_pipeline.py` (orchestrator, sequential request-response)

**Status:** No changes needed. Verify `--from 4` skips steps 1-3, runs steps 4-6 in order.

**Analog:** itself

**--from flag implementation** (lines 160-209):
```python
def run(from_step: int = 1) -> None:
    steps = _load_steps()

    for step_num, step_name, step_fn, target_table in steps:
        if step_num < from_step:
            print(f"\n[{step_num}/6] {step_name} — skipped")
            results.append({..., "status": "skipped", ...})
            continue

        # ... count rows before, call step_fn(), count after, record delta ...
        try:
            step_fn()
        except SystemExit:
            status = "failed"
            failed = True
```

**Step table** (lines 59-66): Steps 4, 5, 6 map to `build_sessions.run`, `compute_features.run`, `label_activities.run` targeting tables `sessions`, `session_features`, `activity_labels`.

**CLI entry point** (lines 235-242):
```python
parser.add_argument(
    "--from", dest="from_step", type=int, default=1,
    help="Step to start from (1-6). Default: 1 (run all)"
)
args = parser.parse_args()
run(from_step=args.from_step)
```

Invocation to use: `python scripts/run_pipeline.py --from 4`

---

### `tests/test_build_sessions.py` (test, optional timezone test addition)

**Status:** Deferred per CONTEXT.md decision D-deferred. If planner includes it as trivial, follow the existing factory + class pattern exactly.

**Analog:** itself

**_plays() factory pattern** (lines 19-25):
```python
def _plays(rows):
    """Build a plays DataFrame from (played_at_iso, duration_ms) tuples."""
    df = pd.DataFrame(rows, columns=["played_at", "duration_ms"])
    df["played_at"] = pd.to_datetime(df["played_at"], utc=True)
    df["track_id"] = [f"t{i}" for i in range(len(df))]
    df["artist_id"] = ["a0"] * len(df)
    return df
```

**Test class structure** (lines 28-99): All tests live inside a class inheriting nothing (`class TestAssignSessions:`). Method names describe the scenario in plain English. No fixtures — factory is called inline per test.

**Timezone test would look like** (follow this structure if added):
```python
class TestBuildSessionRecordsTz:
    def test_hour_of_day_uses_bogota_time_not_utc(self):
        # A play at 05:00 UTC = 00:00 Bogota (UTC-5).
        # hour_of_day must be 0, not 5.
        plays = _plays([("2025-04-01T05:00:00Z", 180_000)])
        assigned = assign_sessions(plays)
        records = build_session_records(assigned)
        assert records[0]["hour_of_day"] == 0, (
            "05:00 UTC must map to midnight Bogota (hour 0), not 5"
        )
```

Import needed: no new imports — `assign_sessions` and `build_session_records` already imported at line 12-16.

---

## Shared Patterns

### Database connection
**Source:** `db/connection.py` lines 67-76
**Apply to:** `transformation/build_sessions.py` (already used as `get_db_connection()`)
```python
def get_connection():
    """Raw psycopg2 connection used by ingestion and transformation scripts."""
    return psycopg2.connect(
        host=POOLER_HOST, port=POOLER_PORT, user=POOLER_USER,
        password=_resolve_password(), dbname=DB_NAME, sslmode=SSL_MODE,
    )
```

### Error handling + exit codes
**Source:** `transformation/build_sessions.py` lines 188-191
**Apply to:** All pipeline scripts
```python
except Exception as e:
    conn.rollback()
    print(f"\nERROR: {e}")
    sys.exit(1)
```
Orchestrator catches `SystemExit` (line 189 of `run_pipeline.py`) to mark step as `"failed"`.

### Print-based logging
**Source:** `transformation/build_sessions.py` lines 159-185
**Apply to:** All transformation modules
```python
print("=== Construccion de sesiones ===")
print(f"Plays cargados: {len(df)}")
print(f"Sesiones detectadas: {len(sessions)}")
for s in sessions:
    print(f"  {s['start_time'][:16]} | {s['duration_minutes']:.1f} min | {s['n_tracks']} tracks")
print(f"\nResumen: {len(sessions)} sesiones insertadas en sessions.")
```

### Idempotent upsert
**Source:** `transformation/build_sessions.py` lines 132-141
**Apply to:** All transformation writers
Pattern: `ON CONFLICT (unique_key) DO UPDATE SET <only mutable columns>` — never touch stable identifiers or foreign keys in the SET clause.

---

## No Analog Found

None. All files to be created or modified have exact analogs in the codebase.

---

## Verification Query

After the re-run, this SQL must return 0 rows (from CONTEXT.md `<specifics>`):

```sql
SELECT session_id, hour_of_day,
       EXTRACT(HOUR FROM start_time AT TIME ZONE 'America/Bogota')::int AS expected_hour,
       hour_of_day - EXTRACT(HOUR FROM start_time AT TIME ZONE 'America/Bogota')::int AS diff
FROM sessions
WHERE hour_of_day != EXTRACT(HOUR FROM start_time AT TIME ZONE 'America/Bogota')::int
LIMIT 20;
```

---

## Metadata

**Analog search scope:** `transformation/`, `scripts/`, `tests/`, `db/`
**Files scanned:** 4 (`build_sessions.py`, `run_pipeline.py`, `test_build_sessions.py`, `db/connection.py`)
**Pattern extraction date:** 2026-04-15
