# Testing

## Framework

- **Runner:** pytest 9.0.3
- **Assertion style:** plain `assert` statements with descriptive messages
- **No mocking library** — isolation via pure functions and `monkeypatch`/`tmp_path` fixtures

## Test Structure

```
tests/
├── conftest.py              # sys.path setup (adds project root)
├── test_build_sessions.py   # transformation.build_sessions
├── test_compute_features.py # transformation.compute_features
├── test_label_activities.py # transformation.label_activities
└── test_run_pipeline.py     # scripts.run_pipeline (formatting helpers)
```

## Coverage Scope

| Module | Test File | What's Covered |
|--------|-----------|----------------|
| `transformation/build_sessions.py` | `test_build_sessions.py` | Session gap splitting, end-time calculation, session ID determinism |
| `transformation/compute_features.py` | `test_compute_features.py` | Skip detection per-session, 50% threshold, edge cases |
| `transformation/label_activities.py` | `test_label_activities.py` | All 4 heuristic rules, duration gates, canonical production sessions |
| `scripts/run_pipeline.py` | `test_run_pipeline.py` | Markdown/text table rendering, step summary writing, warning emission |

**Not covered by unit tests:** ingestion modules (external Spotify API), `db/` layer (live Supabase), dashboard queries.

## Test Patterns

### Factory helpers (per-file, not shared)

Each test file defines its own `_plays()` or `_session()` factory. These build minimal DataFrames/Series with only the fields the function under test reads:

```python
def _plays(rows):
    """Build a plays DataFrame from (played_at_iso, duration_ms) tuples."""
    df = pd.DataFrame(rows, columns=["played_at", "duration_ms"])
    df["played_at"] = pd.to_datetime(df["played_at"], utc=True)
    df["track_id"] = [f"t{i}" for i in range(len(df))]
    df["artist_id"] = ["a0"] * len(df)
    return df

def _session(duration_minutes, hour_of_day, n_skips, day_of_week=2, n_tracks=10):
    return pd.Series({...})
```

### Class-based test grouping

Tests grouped into semantically named classes — not by method but by concept:

```python
class TestAssignSessions:   # tests assign_sessions()
class TestBuildSessionRecords:  # tests build_session_records()
class TestCanonicalScenarios:   # production sessions from ADR
class TestDurationGate:         # gate boundary conditions
class TestCasual:               # casual rule specifics
class TestTieBreakingAndRouting: # rule priority ordering
```

### Canonical scenario tests

`test_label_activities.py::TestCanonicalScenarios` locks in the four real production sessions documented in `docs/decisions/transformation_layer.md`. These serve as regression guards against accidental heuristic changes:

```python
def test_late_night_long_session_is_tasks_with_full_confidence(self):
    label, score = classify_session(_session(103.5, 3, 0))
    assert label == "tasks"
    assert score == pytest.approx(1.0, abs=0.01)
```

### Constant guard tests

Sentinel tests that fail if business-critical constants are changed without updating dependent tests:

```python
def test_threshold_sanity(self):
    assert SESSION_GAP_MINUTES == 30

def test_threshold_is_fifty_percent(self):
    assert SKIP_THRESHOLD == 0.5
```

### File I/O tests with tmp_path

`test_run_pipeline.py` uses `tmp_path` (pytest built-in) and `monkeypatch` to test file writes:

```python
def test_writes_markdown_when_env_var_is_set(self, tmp_path, monkeypatch):
    summary_file = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
    _emit_step_summary(rows, total_s=1.5, failed=False)
    content = summary_file.read_text(encoding="utf-8")
    assert "## Spotify Ingestion Pipeline" in content
```

### stdout capture

`capsys` fixture used for testing GitHub Actions annotation output:

```python
def test_emits_warning_on_zero_new_plays(self, capsys, monkeypatch):
    _emit_warnings([...])
    out = capsys.readouterr().out
    assert "::warning title=No new plays::" in out
```

## Running Tests

```bash
# All tests
pytest

# Single file
pytest tests/test_build_sessions.py

# Single class
pytest tests/test_label_activities.py::TestCanonicalScenarios

# Verbose
pytest -v
```

## Design Philosophy

- **Pure functions first:** transformation layer has zero I/O, making it trivially testable without mocks
- **No database in tests:** ingestion and DB modules are intentionally excluded from unit tests — tested via integration (actual pipeline run)
- **Readable over DRY:** factory helpers duplicated per file rather than shared from conftest — each test file is self-contained
- **Docstrings explain *why*:** test docstrings document business logic (e.g. why 30-min gap, what canonical sessions represent)
