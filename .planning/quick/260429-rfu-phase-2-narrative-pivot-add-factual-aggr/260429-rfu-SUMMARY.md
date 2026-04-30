---
phase: quick-260429-rfu
status: complete
date: 2026-04-30
commits:
  - 56c310c
  - 9faa014
files_modified:
  - dashboard/queries.py
  - dashboard/app.py
---

# Quick Task 260429-rfu — Summary

**Description:** Phase 2 narrative pivot — add factual aggregates to Zone 1

## Requirements addressed

| ID | Requirement | Result |
|----|-------------|--------|
| PIVOT2-01 | `load_plays_by_month` | Done — Bogota-local month buckets, returns plays + minutes |
| PIVOT2-02 | `load_top_artists` | Done — mirror of `load_top_tracks` |
| PIVOT2-03 | `load_diversity_by_month` | Done — `unique_tracks` + `unique_artists` per month |
| PIVOT2-04 | `load_dow_hour_heatmap` | Done — Monday=0 normalized in SQL, densified to 7×24 grid |
| PIVOT2-05 | Listening Patterns 4-row reorg | Done — hero plays-by-month, then 2×2 grid, then heatmap |

## Layout shipped

```
Listening Patterns (FACTS)
├── Row 1 (full)   Plays by Month                          green bars
├── Row 2 (2 col)  Top Tracks    | Top Artists             blue / orange
├── Row 3 (2 col)  Plays by Hour | Diversity by Month      green / two-line
└── Row 4 (full)   Day of Week x Hour Heatmap              greens scale
```

## Architecture decisions

- **Bogota timezone everywhere.** Every aggregation converts `played_at AT TIME ZONE 'America/Bogota'` BEFORE extracting month/dow/hour. Without this, a play at 23:30 Bogota gets bucketed into the next UTC day, distorting late-evening patterns.
- **Day-of-week normalized in SQL.** Postgres `EXTRACT(DOW)` returns Sunday=0, but Python (and `DAY_LABELS` in app.py) uses Monday=0. Normalizing once in SQL with `((dow + 6) % 7)` means the dashboard can use a single `DOW_LABELS_MON0` list without translation logic.
- **Densification in Python, not SQL.** `load_dow_hour_heatmap` lets the DB do the cheap aggregation, then Pandas left-joins a Cartesian 7×24 grid to fill missing buckets. Avoids `generate_series` cross-join in SQL, simpler to read, equivalent result.
- **Track key composition.** `track_name || '||' || artist_name` for unique-track counting — handles songs that share a title across artists. The literal `'||'` separator reduces the (still nonzero) chance of name collision via embedded pipes.
- **Constants at module top.** `DOW_LABELS_MON0` lives next to `DAY_LABELS` rather than inside the heatmap block so it's discoverable when adding new dow-aware charts later.

## Constraints honored

- Two files modified: `dashboard/queries.py` (+98 lines, 0 deletions), `dashboard/app.py` (+172 / −13).
- All other dashboard concerns intact: country map, warning banner, Sessions, Activity by Hour, Day Detail, footer.
- No existing query touched.
- All chart calls use `use_container_width=True` (Streamlit 1.40.2 pinned in `requirements.txt` — `width='stretch'` would crash `st.dataframe` per the lesson learned in Phase 1).
- No Unicode in Python `print()` (none added).
- No Claude attribution in commits.

## Verification

Static (`python -c`):
- Both files parse (`ast.parse`).
- All 4 new accessors (`_plays_by_month`, `_top_artists`, `_diversity_by_month`, `_dow_hour_heatmap`) defined.
- Chart titles "Plays by Month", "Top 10 Artists", "Diversity by Month", "Day of Week x Hour" present.
- `DOW_LABELS_MON0` constant present.
- No `width="stretch"` regression.
- Country map (`choropleth` + `_COUNTRY_NAMES`) and warning banner (`Inferred Activities`) preserved.

Runtime: pending user smoke test on Streamlit Cloud after push (the queries hit live Supabase data).

## Out of scope (Phase 3+)

- New vs repeat tracks per month (needs first-seen subquery)
- "The Rules" panel rendering `transformation/label_activities.py`
- Confidence-score histogram
- Sensitivity analysis (re-label with shifted thresholds)
- Adversarial example picker
- Lineage diagram + assumptions list
