"""
Tests for scripts.run_pipeline monitoring helpers.

These exercise the pure formatting / annotation logic: table
rendering, step summary writes, and warning emission on zero-row
ingestions. No Spotify or DB calls are involved — the helpers take
plain dicts and write to a file/stdout.
"""

import os

import pytest

from scripts.run_pipeline import (
    _emit_step_summary,
    _emit_warnings,
    _format_markdown_table,
    _format_text_table,
)


def _row(step: int, name: str, status: str,
         before=None, after=None, delta=None, duration_s: float = 0.0) -> dict:
    return {
        "step":       step,
        "name":       name,
        "status":     status,
        "before":     before,
        "after":      after,
        "delta":      delta,
        "duration_s": duration_s,
    }


class TestFormatMarkdownTable:
    """The markdown table is what lands in $GITHUB_STEP_SUMMARY."""

    def test_renders_header_and_one_row(self):
        out = _format_markdown_table([
            _row(1, "Ingest plays", "ok", before=100, after=110, delta=10, duration_s=2.34),
        ])
        assert "| # | Step | Status |" in out
        assert "Ingest plays" in out
        assert ":white_check_mark: ok" in out
        # Delta is bolded so the eye lands on new rows first
        assert "**+10**" in out
        assert "2.3s" in out

    def test_failed_row_uses_x_icon(self):
        out = _format_markdown_table([
            _row(2, "Build sessions", "failed", before=4, after=4, delta=0),
        ])
        assert ":x: failed" in out

    def test_skipped_row_uses_fast_forward_icon(self):
        out = _format_markdown_table([
            _row(3, "Label activities", "skipped"),
        ])
        assert ":fast_forward: skipped" in out
        # None values collapse to "-" so the table stays aligned
        assert "| - | - | - |" in out

    def test_negative_delta_still_bolded(self):
        # Not a real case today, but the formatter should handle it.
        out = _format_markdown_table([
            _row(1, "Ingest plays", "ok", before=10, after=8, delta=-2, duration_s=1.0),
        ])
        assert "**-2**" in out


class TestFormatTextTable:
    """Plain-text variant printed to stdout in both local and CI runs."""

    def test_contains_header_and_row(self):
        out = _format_text_table([
            _row(1, "Ingest plays", "ok", before=0, after=10, delta=10, duration_s=1.2),
        ])
        lines = out.splitlines()
        assert lines[0].startswith(" #")
        assert "Ingest plays" in out
        assert "+10" in out


class TestEmitStepSummary:
    """
    When GITHUB_STEP_SUMMARY points at a file, the summary is appended.
    When unset (local runs), the helper must be a no-op.
    """

    def test_writes_markdown_when_env_var_is_set(self, tmp_path, monkeypatch):
        summary_file = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

        rows = [_row(1, "Ingest plays", "ok", before=0, after=5, delta=5, duration_s=1.0)]
        _emit_step_summary(rows, total_s=1.5, failed=False)

        content = summary_file.read_text(encoding="utf-8")
        assert "## Spotify Ingestion Pipeline" in content
        assert ":white_check_mark: **Pipeline OK**" in content
        assert "1.5s" in content
        assert "Ingest plays" in content

    def test_writes_failed_banner_when_failed(self, tmp_path, monkeypatch):
        summary_file = tmp_path / "summary.md"
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

        rows = [_row(1, "Ingest plays", "failed", before=0, after=0, delta=0)]
        _emit_step_summary(rows, total_s=0.5, failed=True)

        content = summary_file.read_text(encoding="utf-8")
        assert ":x: **Pipeline FAILED**" in content

    def test_no_op_when_env_var_is_missing(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        # Must not raise even though there's no file to write to.
        _emit_step_summary(
            [_row(1, "Ingest plays", "ok", before=0, after=0, delta=0)],
            total_s=0.1, failed=False,
        )

    def test_appends_rather_than_overwrites(self, tmp_path, monkeypatch):
        # GitHub Actions reuses the same summary file across steps —
        # we must append so earlier output is preserved.
        summary_file = tmp_path / "summary.md"
        summary_file.write_text("# earlier step\n\n", encoding="utf-8")
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))

        _emit_step_summary(
            [_row(1, "Ingest plays", "ok", before=0, after=1, delta=1)],
            total_s=0.1, failed=False,
        )

        content = summary_file.read_text(encoding="utf-8")
        assert content.startswith("# earlier step")
        assert "Spotify Ingestion Pipeline" in content


class TestEmitWarnings:
    """
    A zero-plays ingestion in step 1 is the canary for an expired OAuth
    token or a Spotify outage — both conditions that let the job exit 0
    while silently stopping the data flow. The warning annotation
    surfaces it on the GitHub run page.
    """

    def test_emits_warning_on_zero_new_plays(self, capsys, monkeypatch):
        monkeypatch.setenv("GITHUB_ACTIONS", "true")

        _emit_warnings([_row(1, "Ingest plays", "ok", before=100, after=100, delta=0)])

        out = capsys.readouterr().out
        assert "::warning title=No new plays::" in out
        assert "Spotify token may be expired" in out

    def test_no_warning_when_delta_is_positive(self, capsys, monkeypatch):
        monkeypatch.setenv("GITHUB_ACTIONS", "true")

        _emit_warnings([_row(1, "Ingest plays", "ok", before=100, after=110, delta=10)])

        assert "::warning" not in capsys.readouterr().out

    def test_no_warning_when_step_1_failed(self, capsys, monkeypatch):
        # A failure is a louder signal — the job already exits non-zero.
        # The warning is specifically for the silent "ok but empty" case.
        monkeypatch.setenv("GITHUB_ACTIONS", "true")

        _emit_warnings([_row(1, "Ingest plays", "failed", before=100, after=100, delta=0)])

        assert "::warning" not in capsys.readouterr().out

    def test_zero_rows_in_other_steps_are_not_warnings(self, capsys, monkeypatch):
        # Transformation steps can legitimately be a no-op (same input
        # produces same output under idempotent upserts).
        monkeypatch.setenv("GITHUB_ACTIONS", "true")

        _emit_warnings([_row(4, "Build sessions", "ok", before=10, after=10, delta=0)])

        assert "::warning" not in capsys.readouterr().out

    def test_local_run_uses_plain_warning_text(self, capsys, monkeypatch):
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)

        _emit_warnings([_row(1, "Ingest plays", "ok", before=5, after=5, delta=0)])

        out = capsys.readouterr().out
        assert "::warning" not in out
        assert "WARNING:" in out
