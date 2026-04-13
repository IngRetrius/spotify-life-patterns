"""
Heuristic activity labeling per session.

Labels produced: casual, shower, gym, tasks
                 (+ 'unknown' when no rule clears the confidence threshold)

Each rule returns a score in [0, 1]. The rule with the highest score wins.
If none crosses MIN_CONFIDENCE -> 'unknown'.

Signals available (no audio features due to Spotify API restriction):
- duration_minutes : total session duration
- n_tracks         : number of tracks
- n_skips          : tracks listened to less than 50%
- hour_of_day      : start hour (0-23)
- day_of_week      : 0=Monday, 6=Sunday

Scoring model: duration-gated
-----------------------------
Each routine rule (shower, gym, tasks) has a duration band that acts
as a gate. Sessions outside the band score 0 on that rule, no matter
how the other signals look. This prevents the failure mode where
time-of-day + zero-skips bonuses push a short, unrelated session over
the threshold of a routine it clearly does not match.

Sessions that fail every routine gate but are very short or have very
few tracks are captured by `casual` — opened Spotify briefly, no
routine inferred.

Usage:
    python transformation/label_activities.py
"""

import sys
import pandas as pd
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.connection import get_connection as get_db_connection

load_dotenv()

# ── Hour windows per activity ─────────────────────────────────────────────────
# Defined as sets for O(1) lookup.

SHOWER_HOURS      = set(range(6, 11))  | set(range(20, 24))   # 6-10h and 20-23h
GYM_HOURS         = set(range(5, 11))  | set(range(16, 23))   # 5-10h and 16-22h
NIGHT_STUDY_HOURS = set(range(22, 24)) | set(range(0, 6))     # 22-23h and 0-5h

# ── Duration gates ────────────────────────────────────────────────────────────
# Sessions outside these bands cannot score for the rule, regardless
# of hour or skip signals. This is what makes the scoring robust:
# the primary signal (duration) must match for any secondary signal
# to matter.

SHOWER_DURATION = (5, 20)        # minutes
GYM_DURATION    = (35, 110)
TASKS_DURATION  = (40, 300)      # 5h upper cap filters overnight drift

# Casual listening: very short OR very few tracks.
CASUAL_MAX_MINUTES = 5
CASUAL_MAX_TRACKS  = 2

MIN_CONFIDENCE = 0.4


# ── Data loading ──────────────────────────────────────────────────────────────

def load_sessions_with_features(conn) -> pd.DataFrame:
    """Join sessions with session_features into a single DataFrame."""
    query = """
        SELECT
            s.session_id,
            s.duration_minutes,
            s.n_tracks,
            s.hour_of_day,
            s.day_of_week,
            sf.n_skips
        FROM sessions s
        LEFT JOIN session_features sf ON s.session_id = sf.session_id
    """
    df = pd.read_sql(query, conn)
    df["n_skips"] = df["n_skips"].fillna(0).astype(int)
    return df


# ── Heuristic rules ───────────────────────────────────────────────────────────

def rule_shower(row: pd.Series) -> float:
    """
    Shower: short session in grooming hours, no skips (hands-free).

    Gate: duration must fall in the shower band.
    Base: 0.5 once gated. Bonuses total up to +0.5.
    Max score: 1.0
    """
    lo, hi = SHOWER_DURATION
    if not (lo <= row["duration_minutes"] <= hi):
        return 0.0                                      # gate

    score = 0.5
    if row["n_skips"] == 0:                  score += 0.3   # can't touch the phone
    if row["hour_of_day"] in SHOWER_HOURS:   score += 0.2   # grooming hours
    return score


def rule_gym(row: pd.Series) -> float:
    """
    Gym: training-duration session with continuous music, at gym hours.

    Gate: duration must fall in the workout band (35-110 min).
    Max score: 1.0
    """
    lo, hi = GYM_DURATION
    if not (lo <= row["duration_minutes"] <= hi):
        return 0.0                                      # gate

    score = 0.4
    if row["n_skips"] <= 2:                  score += 0.3   # continuous music
    if row["hour_of_day"] in GYM_HOURS:      score += 0.3   # 5-10am or 4-10pm
    return score


def rule_tasks(row: pd.Series) -> float:
    """
    Tasks / focused work: long session with background music.

    Gate: duration in (40, 300) min — longer than 5h is almost certainly
    accidental playback, not real focused listening.
    Max score: 1.0
    """
    lo, hi = TASKS_DURATION
    if not (lo <= row["duration_minutes"] <= hi):
        return 0.0                                      # gate

    score = 0.5
    if row["n_skips"] <= 5:                      score += 0.2   # background music
    if row["hour_of_day"] in NIGHT_STUDY_HOURS:  score += 0.3   # late-night focus
    return score


def rule_casual(row: pd.Series) -> float:
    """
    Casual listening: user opened Spotify briefly and moved on.

    Not a routine. Captures the sessions that would otherwise be
    mislabeled by weak secondary signals alone (e.g. 2.6-min session at
    23h with 0 skips — previously mislabeled as 'shower' because the hour
    bonus + zero-skips bonus alone crossed 0.4).

    Gate: very short (< 5 min) OR very few tracks (<= 2).
    Max score: 0.7 — intentionally lower than the routine rules so a
    legitimate shower or gym session still wins when both gates open.
    """
    if not (row["duration_minutes"] < CASUAL_MAX_MINUTES
            or row["n_tracks"] <= CASUAL_MAX_TRACKS):
        return 0.0                                      # gate

    score = 0.5
    if row["n_skips"] >= 1:                  score += 0.2   # exploratory behavior
    return score


# Order matters for tie-breaking: max() returns the first key with the
# max value when iterating a dict. Routine rules come first so a true
# shower / gym / tasks session wins a 0.5 tie against casual.
RULES = {
    "shower": rule_shower,
    "gym":    rule_gym,
    "tasks":  rule_tasks,
    "casual": rule_casual,
}


def classify_session(row: pd.Series) -> tuple[str, float]:
    """
    Apply all rules and return the (label, confidence) with the max score.
    If none crosses MIN_CONFIDENCE -> 'unknown'.
    """
    scores = {label: fn(row) for label, fn in RULES.items()}
    best_label = max(scores, key=scores.get)
    best_score = round(scores[best_label], 2)

    if best_score < MIN_CONFIDENCE:
        return "unknown", best_score

    return best_label, best_score


# ── Database write ────────────────────────────────────────────────────────────

UPSERT_LABELS_SQL = """
    INSERT INTO activity_labels (session_id, activity_label, confidence_score, labeling_method)
    VALUES (%(session_id)s, %(activity_label)s, %(confidence_score)s, %(labeling_method)s)
    ON CONFLICT (session_id) DO UPDATE SET
        activity_label   = EXCLUDED.activity_label,
        confidence_score = EXCLUDED.confidence_score;
"""


def upsert_labels(cursor, labels: list[dict]) -> None:
    if not labels:
        return
    psycopg2.extras.execute_batch(cursor, UPSERT_LABELS_SQL, labels, page_size=100)


# ── Orchestration ─────────────────────────────────────────────────────────────

def run() -> None:
    print("=== Activity labeling ===")

    conn = get_db_connection()
    conn.autocommit = False
    cursor = conn.cursor()

    try:
        df = load_sessions_with_features(conn)

        if df.empty:
            print("No sessions found. Run build_sessions.py first.")
            return

        labels = []
        for _, row in df.iterrows():
            label, confidence = classify_session(row)
            labels.append({
                "session_id":       row["session_id"],
                "activity_label":   label,
                "confidence_score": confidence,
                "labeling_method":  "heuristic",
            })

        upsert_labels(cursor, labels)
        conn.commit()

        print(f"{len(labels)} sessions labeled:\n")
        print(f"  {'Session':<10} {'Dur':>8} {'Hour':>5} {'Skips':>6}  {'Activity':<12} {'Score':>6}")
        print(f"  {'-'*55}")
        for i, (_, row) in enumerate(df.iterrows()):
            lbl = labels[i]
            print(
                f"  {lbl['session_id'][:8]}...  "
                f"{row['duration_minutes']:>6.1f}m  "
                f"{row['hour_of_day']:>3}h  "
                f"{row['n_skips']:>5}  "
                f"  {lbl['activity_label']:<12}  "
                f"{lbl['confidence_score']:>5.2f}"
            )

        print(f"\nSummary: {len(labels)} labels written to activity_labels.")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        sys.exit(1)

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    run()
