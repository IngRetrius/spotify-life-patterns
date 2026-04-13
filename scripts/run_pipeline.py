"""
Pipeline orchestrator.

Runs the 6 steps in order:
  1. Ingest plays
  2. Ingest audio features
  3. Ingest artists
  4. Build sessions
  5. Compute session features
  6. Label activities

Observability:
- Before and after each step, counts rows in that step's target table.
- The delta is the number of rows added by this run.
- Results are printed as a table to stdout, and (when running in GitHub
  Actions) appended as markdown to $GITHUB_STEP_SUMMARY so the run page
  shows the same table without digging through logs.
- If step 1 produced 0 new plays, emits a GitHub Actions warning
  annotation (Spotify token expired or API error). The job still exits
  with the correct status from the underlying steps.

Usage:
    python scripts/run_pipeline.py              # full pipeline
    python scripts/run_pipeline.py --from 4     # transformation only (steps 4-6)
"""

import argparse
import os
import sys
import time

from dotenv import load_dotenv

sys.path.insert(0, ".")

from db.connection                   import get_connection
from ingestion.ingest_plays          import run as run_plays
from ingestion.ingest_audio_features import run as run_audio_features
from ingestion.ingest_artists        import run as run_artists
from transformation.build_sessions   import run as run_build_sessions
from transformation.compute_features import run as run_compute_features
from transformation.label_activities import run as run_label_activities


load_dotenv()


# (step_num, display name, callable, target table for row counting)
STEPS = [
    (1, "Ingest plays",            run_plays,            "raw_plays"),
    (2, "Ingest audio features",   run_audio_features,   "raw_audio_features"),
    (3, "Ingest artists",          run_artists,          "raw_artists"),
    (4, "Build sessions",          run_build_sessions,   "sessions"),
    (5, "Compute session features", run_compute_features, "session_features"),
    (6, "Label activities",        run_label_activities, "activity_labels"),
]


def _count_rows(table: str) -> int | None:
    """Return COUNT(*) of a table, or None if the query fails."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        (n,) = cur.fetchone()
        cur.close()
        conn.close()
        return int(n)
    except Exception as e:
        print(f"  WARN: could not count rows in {table}: {e}")
        return None


def _format_markdown_table(rows: list[dict]) -> str:
    """Render the per-step results as a GitHub-flavored markdown table."""
    header = (
        "| # | Step | Status | Before | After | New rows | Duration |\n"
        "|---|------|--------|--------|-------|----------|----------|\n"
    )
    body_lines = []
    for r in rows:
        before = "-" if r["before"] is None else str(r["before"])
        after  = "-" if r["after"]  is None else str(r["after"])
        delta  = "-" if r["delta"]  is None else f"**{r['delta']:+d}**"
        status_icon = {
            "ok":      ":white_check_mark: ok",
            "failed":  ":x: failed",
            "skipped": ":fast_forward: skipped",
        }[r["status"]]
        body_lines.append(
            f"| {r['step']} | {r['name']} | {status_icon} "
            f"| {before} | {after} | {delta} | {r['duration_s']:.1f}s |"
        )
    return header + "\n".join(body_lines) + "\n"


def _format_text_table(rows: list[dict]) -> str:
    """Plain-text version of the same table for stdout."""
    header = f"{'#':>2}  {'Step':<28}  {'Status':<8}  {'Before':>7}  {'After':>6}  {'New':>5}  {'Time':>6}"
    sep    = "-" * len(header)
    lines  = [header, sep]
    for r in rows:
        before = "-" if r["before"] is None else str(r["before"])
        after  = "-" if r["after"]  is None else str(r["after"])
        delta  = "-" if r["delta"]  is None else f"{r['delta']:+d}"
        lines.append(
            f"{r['step']:>2}  {r['name']:<28}  {r['status']:<8}  "
            f"{before:>7}  {after:>6}  {delta:>5}  {r['duration_s']:>5.1f}s"
        )
    return "\n".join(lines)


def _emit_step_summary(rows: list[dict], total_s: float, failed: bool) -> None:
    """Write the markdown summary to $GITHUB_STEP_SUMMARY, if present."""
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return

    status_line = (
        ":x: **Pipeline FAILED**" if failed else ":white_check_mark: **Pipeline OK**"
    )
    markdown = (
        f"## Spotify Ingestion Pipeline\n\n"
        f"{status_line} — total {total_s:.1f}s\n\n"
        f"{_format_markdown_table(rows)}\n"
    )
    try:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(markdown)
    except Exception as e:
        print(f"WARN: could not write GITHUB_STEP_SUMMARY: {e}")


def _emit_warnings(rows: list[dict]) -> None:
    """Emit GitHub Actions ::warning:: annotations for suspicious conditions."""
    in_actions = os.getenv("GITHUB_ACTIONS") == "true"
    for r in rows:
        if r["step"] == 1 and r["status"] == "ok" and r["delta"] == 0:
            msg = (
                "Step 1 (Ingest plays) inserted 0 new rows. "
                "Spotify token may be expired, rate-limited, or the user "
                "has no new listening activity since the last run."
            )
            if in_actions:
                print(f"::warning title=No new plays::{msg}")
            else:
                print(f"WARNING: {msg}")


def run(from_step: int = 1) -> None:
    print("=" * 60)
    print("   SPOTIFY LIFE PATTERNS — PIPELINE")
    print("=" * 60)

    pipeline_start = time.time()
    results: list[dict] = []
    failed = False

    for step_num, step_name, step_fn, target_table in STEPS:
        if step_num < from_step:
            print(f"\n[{step_num}/6] {step_name} — skipped")
            results.append({
                "step": step_num, "name": step_name, "status": "skipped",
                "before": None, "after": None, "delta": None, "duration_s": 0.0,
            })
            continue

        print(f"\n[{step_num}/6] {step_name}")
        print("-" * 40)

        before = _count_rows(target_table)
        step_start = time.time()
        status = "ok"

        try:
            step_fn()
        except SystemExit:
            # Step scripts call sys.exit(1) on error
            status = "failed"
            failed = True

        duration = time.time() - step_start
        after = _count_rows(target_table)
        delta = None if (before is None or after is None) else (after - before)

        results.append({
            "step": step_num, "name": step_name, "status": status,
            "before": before, "after": after, "delta": delta,
            "duration_s": duration,
        })

        if status == "failed":
            print(f"[FAIL] Step {step_num} failed. Stopping pipeline.")
            break

        delta_str = f"{delta:+d}" if delta is not None else "unknown"
        print(f"[OK] {duration:.1f}s | new rows in {target_table}: {delta_str}")

    # Fill in skipped results for steps that never ran because of a failure
    processed = {r["step"] for r in results}
    for step_num, step_name, _, _ in STEPS:
        if step_num not in processed:
            results.append({
                "step": step_num, "name": step_name, "status": "skipped",
                "before": None, "after": None, "delta": None, "duration_s": 0.0,
            })
    results.sort(key=lambda r: r["step"])

    total = time.time() - pipeline_start

    print("\n" + "=" * 60)
    print(f"Pipeline {'FAILED' if failed else 'OK'} in {total:.1f}s")
    print("=" * 60)
    print(_format_text_table(results))

    _emit_step_summary(results, total, failed)
    _emit_warnings(results)

    if failed:
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Spotify Life Patterns pipeline")
    parser.add_argument(
        "--from", dest="from_step", type=int, default=1,
        help="Step to start from (1-6). Default: 1 (run all)"
    )
    args = parser.parse_args()
    run(from_step=args.from_step)
