---
phase: quick-260430-0nd
plan: 01
subsystem: dashboard
tags: [dashboard, methodology, graphviz, lineage]
requires: []
provides:
  - "Methodology data lineage diagram with Supabase cluster + Python pipeline node"
affects:
  - dashboard/app.py
tech_stack:
  added: []
  patterns:
    - "graphviz subgraph cluster to group storage-layer nodes"
key_files:
  created: []
  modified:
    - dashboard/app.py
decisions:
  - "Wrap raw_plays/sessions/session_features/activity_labels inside subgraph cluster_supabase to make storage-vs-compute separation visible"
  - "Introduce a single 'Python pipeline' node (blue) instead of one node per script, since the architectural truth is one batch job that reads/writes Supabase repeatedly"
  - "Use bgcolor='#ffffff00' (transparent fill) on the cluster so the dashboard background shows through (Streamlit dark/light theme safe)"
  - "Add explicit 'upsert' edges back into the cluster to surface that every transformation step writes back into Supabase"
metrics:
  duration: ~3min
  completed: 2026-04-30
---

# Quick Task 260430-0nd: Update Methodology Data Lineage Digraph Summary

One-liner: Restructured the Methodology section's graphviz lineage diagram in `dashboard/app.py` so the four analytics tables visibly live inside a `Supabase (PostgreSQL)` cluster, with a separate `Python pipeline` node mediating every read/write — preserving all original edge labels and color coding.

## What Changed

Single-file edit in `dashboard/app.py`, inside the `st.graphviz_chart(...)` call in the Methodology section.

- Before: lines 1138-1162 contained a flat digraph with 6 sibling nodes (`api`, `raw`, `sess`, `feat`, `lab`, `ui`) and 7 edges, where pipeline scripts only existed as edge labels.
- After: lines 1138-1178 contain a digraph with:
  - A `subgraph cluster_supabase` (label `"Supabase (PostgreSQL)"`, dashed rounded border, transparent fill) wrapping `raw`, `sess`, `feat`, `lab`.
  - A `pipeline` node (label `"Python pipeline\n(ingest + transform scripts)"`, blue `#e3f2fd`) outside the cluster.
  - 11 edges encoding the read-transform-write loop: `api -> pipeline -> raw`, then for each transformation step `<table> -> pipeline -> <next_table>` with `upsert` labels on the writebacks.
  - The two original dashed direct edges from `raw` and `sess` to `ui`, plus `lab -> ui`.

## DOT Structure (After)

```
digraph lineage {
    rankdir=TB;
    bgcolor="transparent";
    node [shape=box, style="rounded,filled", ...];
    edge [...];

    api      [label="Spotify Web API", fillcolor="#e8f5e9"];
    pipeline [label="Python pipeline\n(ingest + transform scripts)", fillcolor="#e3f2fd"];
    ui       [label="Dashboard\n(Streamlit)", fillcolor="#e3f2fd"];

    subgraph cluster_supabase {
        label="Supabase (PostgreSQL)";
        style="rounded,dashed";
        color="#6c757d";
        bgcolor="#ffffff00";
        raw  [label="raw_plays\n(...)",         fillcolor="#e8f5e9"];
        sess [label="sessions\n(...)",          fillcolor="#fff3cd"];
        feat [label="session_features\n(...)",  fillcolor="#fff3cd"];
        lab  [label="activity_labels\n(...)",   fillcolor="#fde7e7"];
    }

    api      -> pipeline [label="ingest_plays.py\n(API restrictions)"];
    pipeline -> raw      [label="upsert"];
    raw      -> pipeline [label="build_sessions.py\n(arbitrary 30-min boundary)"];
    pipeline -> sess     [label="upsert"];
    sess     -> pipeline [label="compute_features.py"];
    pipeline -> feat     [label="upsert"];
    feat     -> pipeline [label="label_activities.py\n(heuristic, NOT measurement)"];
    pipeline -> lab      [label="upsert"];
    lab      -> ui;
    sess     -> ui       [style=dashed];
    raw      -> ui       [style=dashed];
}
```

## Preserved Invariants (Verified)

| Invariant | Verified |
|-----------|----------|
| `dashboard/app.py` parses as valid Python | Yes (`ast.parse` succeeded) |
| `subgraph cluster_supabase` present | Yes |
| Cluster label `"Supabase (PostgreSQL)"` present | Yes |
| `Python pipeline` node present | Yes |
| Edge label `30-min gap` preserved | Yes |
| Edge label `<50% completion` preserved | Yes |
| Edge label `5 hand-coded rules` preserved | Yes |
| Edge label `API restrictions` preserved | Yes |
| Edge label `heuristic, NOT measurement` preserved | Yes |
| Fillcolor `#e8f5e9` (green = factual) preserved on `raw` | Yes |
| Fillcolor `#fff3cd` (yellow = derived) preserved on `sess` and `feat` | Yes |
| Fillcolor `#fde7e7` (red = heuristic) preserved on `lab` | Yes |
| Trailing `st.caption(...)` legend untouched | Yes (unchanged in diff) |
| Footer caption `"Spotify API -> Supabase (PostgreSQL) -> Streamlit"` untouched | Yes |
| Only `dashboard/app.py` modified | Yes (`git diff --name-only`) |
| Columns layout `[3, 2]` and assumptions panel untouched | Yes (unchanged in diff) |

## Deviations from Plan

None — plan executed exactly as written.

## Visual Rendering Notes

Manual visual confirmation on dashboard reload is expected as the final check (per plan `<done>` criteria). Graphviz syntax is well-formed: cluster names must begin with `cluster_` to render as a boxed group (satisfied), `bgcolor="#ffffff00"` is a valid 8-digit RGBA hex Graphviz accepts for transparency, and all edge endpoints reference declared nodes.

## Commits

- `5b10b80` feat(quick-260430-0nd-01): group lineage tables in Supabase cluster + Python pipeline node

## Self-Check: PASSED

- `dashboard/app.py` exists and was modified: FOUND
- Commit `5b10b80` exists in git log: FOUND
- All grep invariants in verification block returned OK
