---
phase: quick-260429-lyn
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - dashboard/app.py
autonomous: true
requirements:
  - PIVOT-01-remove-misleading-kpi
  - PIVOT-02-strip-confidence-progressbar
  - PIVOT-03-reorder-three-zone-layout
  - PIVOT-04-add-warning-banner
  - PIVOT-05-rewrite-header-and-promote-missing-data-note

must_haves:
  truths:
    - "Overview KPI grid shows exactly 3 cards (Total Plays, Listening Time, Sessions Detected); 'Top Activity' is gone"
    - "Confidence column in both sessions tables (main + Day Detail) renders as a plain rounded numeric value, not a progress bar"
    - "Sections render in this top-to-bottom order: Overview, Listening Patterns (plays-by-hour + top tracks only), Global Footprint, Warning banner, Sessions, Activity by Hour, Day Detail"
    - "A visually distinct warning banner with amber/yellow styling appears immediately before the Sessions section, titled 'Inferred Activities — Heuristic, Not Measurement'"
    - "Warning banner body explains the heuristic basis (hand-coded rules, not probabilistic), AND includes the 2024 audio-features-restriction note (currently in footer)"
    - "Header subtitle frames the dual narrative (honest data + case study on naive transformations), replacing the 'inferred from history' subtitle"
    - "Country choropleth + country bar in Global Footprint section render byte-identically to the prior version (zero diff in that block)"
  artifacts:
    - path: "dashboard/app.py"
      provides: "Reorganized dashboard with 3-zone narrative (facts → warning → inferences → drill-down)"
      contains: "warning-banner"
  key_links:
    - from: "Overview section KPIs"
      to: "kpis dict from _kpis()"
      via: "3-column st.columns layout"
      pattern: "st\\.columns\\(3\\)"
    - from: "Sessions table column_config"
      to: "Confidence column rendering"
      via: "st.column_config.NumberColumn (replacing ProgressColumn)"
      pattern: "NumberColumn"
    - from: "Warning banner CSS class"
      to: "Banner markdown div above Sessions section"
      via: "st.markdown with unsafe_allow_html=True"
      pattern: "warning-banner"
---

<objective>
Pivot the dashboard's narrative from "I detected your real-life activities" to "Honest listening data + a case study in how naive transformations create false confidence." This is Phase 1 of a multi-phase pivot — strictly REMOVE misleading visual cues, REORDER sections into a 3-zone structure (facts → inferences → drill-down), and INSERT a warning banner that frames the inference zone.

Purpose: Stop overstating confidence in heuristic activity inferences. Set the visual scaffold so later phases can plug in the rules panel, sensitivity analysis, and lineage diagram without re-architecting the layout.

Output: A modified `dashboard/app.py` that ships the new layout with no changes to queries, transformations, schema, or the country-map block.
</objective>

<execution_context>
@$HOME/.claude-personal-personal/get-shit-done/workflows/execute-plan.md
@$HOME/.claude-personal-personal/get-shit-done/templates/summary.md
</execution_context>

<context>
@CLAUDE.md
@.planning/STATE.md
@dashboard/app.py

<interfaces>
<!-- Key contracts the executor needs. Extracted from dashboard/app.py. -->
<!-- No need to explore queries.py or transformation/ — only app.py is touched. -->

Functions already defined in app.py (DO NOT modify their signatures):
```python
def section(title: str) -> None: ...
def kpi_card(value: str, label: str, accent: bool = False) -> str: ...
def format_sessions_table(df: pd.DataFrame) -> pd.DataFrame: ...
```

Data accessors (cached, DO NOT change cache decorators or TTLs):
```python
_kpis() -> dict      # keys: total_plays, total_minutes, total_sessions, top_activity (still loaded; just stop displaying)
_sessions_page(page, page_size) -> pd.DataFrame
_sessions_count() -> int
_sessions_for_day(day) -> pd.DataFrame
_top_tracks() -> pd.DataFrame
_plays_by_hour() -> pd.DataFrame
_activity_counts() -> pd.DataFrame
_available_dates() -> pd.DataFrame
_activity_by_hour() -> pd.DataFrame
_plays_for_day(day) -> pd.DataFrame
_plays_by_country() -> pd.DataFrame
```

Existing CSS classes in the `<style>` block (extend, don't replace):
- `.section-label` — section header pill
- `.kpi-card`, `.kpi-value`, `.kpi-label`, `.kpi-accent` — KPI card styling

Streamlit column_config alternatives for Confidence:
- `st.column_config.NumberColumn(label, format="%.2f")` — plain numeric, no bar
</interfaces>
</context>

<tasks>

<task type="auto">
  <name>Task 1: Trim KPI grid, replace ProgressColumn, rewrite header, add warning banner CSS</name>
  <files>dashboard/app.py</files>
  <action>
    Make four targeted edits in `dashboard/app.py`. Do NOT touch any other file.

    1. **Header subtitle rewrite (`app.py:232-236`).**
       Replace the existing `st.markdown("Listening sessions inferred from Spotify history — activities labeled with heuristic rules.")` call with a subtitle that frames the dual narrative. Use exactly:
       ```
       Honest listening data + a case study in how naive transformations create false confidence.
       ```
       Keep the `## Spotify Life Patterns` title line and the `st.divider()` line unchanged.

    2. **Overview KPI grid: 4 cols → 3 cols (`app.py:247-251`).**
       - Change `col1, col2, col3, col4 = st.columns(4)` to `col1, col2, col3 = st.columns(3)`.
       - Delete the `col4.markdown(kpi_card(kpis["top_activity"].capitalize(), "Top Activity", accent=True), ...)` line entirely.
       - DO NOT change the `_kpis()` accessor or the `kpis = _kpis()` lookup — `top_activity` continues to load, we just stop rendering it.
       - Keep `total_plays`, `time_str`, and `total_sessions` cards exactly as-is.

    3. **Replace ProgressColumn with NumberColumn in BOTH sessions tables.**
       At `app.py:314-321` (main sessions table) and `app.py:382-389` (Day Detail's day_sessions table), the `column_config={ "Confidence": st.column_config.ProgressColumn(...) }` block must become:
       ```python
       column_config={
           "Confidence": st.column_config.NumberColumn(
               "Confidence",
               format="%.2f",
               help="Heuristic rule-match score, not a calibrated probability.",
           ),
       },
       ```
       The `format_sessions_table` helper already calls `.round(2)` on `confidence_score` (line 212), so the displayed value is correct — we are only changing the rendering widget.

    4. **Add warning-banner CSS class to the existing `<style>` block (`app.py:52-92`).**
       Inside the same `st.markdown("""<style>...</style>""", unsafe_allow_html=True)` block, append (before the closing `</style>`) a new rule:
       ```css
       .warning-banner {
           background: #fff8e1;
           border-left: 4px solid #f5a623;
           border-radius: 6px;
           padding: 1rem 1.25rem;
           margin: 0.5rem 0 1.25rem 0;
           color: #5d4a00;
           font-size: 0.92rem;
           line-height: 1.5;
       }
       .warning-banner .warning-title {
           font-size: 0.95rem;
           font-weight: 700;
           letter-spacing: 0.02em;
           margin-bottom: 0.4rem;
           color: #8a6500;
       }
       .warning-banner p { margin: 0.35rem 0; }
       ```
       Do not modify the existing `.section-label`, `.kpi-card`, `.kpi-value`, `.kpi-label`, or `.kpi-accent` rules.

    Decision rationale:
    - NumberColumn (not TextColumn) preserves right-aligned numeric formatting and keeps sortability.
    - Amber `#f5a623` left-border + `#fff8e1` background mirror common Streamlit warning conventions without requiring `st.warning()` (which has a different visual weight).
    - Hardcoding the subtitle string here (rather than via a constant) keeps the diff small and reviewable.
  </action>
  <verify>
    <automated>python -c "import ast,sys; tree=ast.parse(open('dashboard/app.py',encoding='utf-8').read()); src=open('dashboard/app.py',encoding='utf-8').read(); assert 'top_activity' not in src.split('# ── 1. KPIs')[1].split('# ── 2.')[0] if False else True; assert 'ProgressColumn' not in src, 'ProgressColumn still present'; assert 'NumberColumn' in src, 'NumberColumn missing'; assert 'warning-banner' in src, 'warning-banner CSS missing'; assert 'st.columns(3)' in src, '3-col KPI grid missing'; assert 'case study' in src, 'new subtitle missing'; print('OK')"</automated>
  </verify>
  <done>
    - `dashboard/app.py` parses cleanly (no syntax error).
    - String `ProgressColumn` no longer appears anywhere in the file.
    - String `NumberColumn` appears at least twice (one per sessions table).
    - String `warning-banner` appears in the CSS block.
    - The Overview section uses `st.columns(3)` and the `col4.markdown(... "Top Activity" ...)` line is gone.
    - Header subtitle contains the phrase "case study".
  </done>
</task>

<task type="auto">
  <name>Task 2: Reorder layout into 3-zone structure and insert warning banner</name>
  <files>dashboard/app.py</files>
  <action>
    Reorder the Layout section of `dashboard/app.py` (everything after `st.divider()` at line 237) into the new section sequence. This is a cut-and-paste reordering — no logic changes inside any block.

    **New order (top to bottom):**

    1. **Overview** — the 3-KPI grid from Task 1 (already correct after Task 1).

    2. **Listening Patterns** (FACTS only) — the existing block currently at `app.py:407-453`:
       - `section("Listening Patterns")`
       - `col_hour, col_tracks = st.columns(2, gap="large")`
       - `with col_hour:` block (plays-by-hour bar chart, lines ~413-427)
       - `with col_tracks:` block (top 10 tracks, lines ~429-453)
       - **STOP HERE.** Do NOT include the `act_hour_df = _activity_by_hour()` block (lines ~455-484) — that moves to the inference zone in step 5.

    3. **Global Footprint** — the existing block at `app.py:486-584` MUST be moved here BYTE-IDENTICALLY. Includes:
       - `st.markdown("<br>", unsafe_allow_html=True)` spacer
       - `section("Global Footprint")`
       - `_COUNTRY_NAMES` dict
       - `country_df = _plays_by_country()`
       - the entire `if not country_df.empty:` block with choropleth + bar chart
       Do NOT modify any code inside this block. Constraint from user: country map preserved exactly as-is.

    4. **Warning banner** — insert directly after Global Footprint, before the Sessions section. Use:
       ```python
       st.markdown("<br>", unsafe_allow_html=True)
       st.markdown(
           """
           <div class="warning-banner">
               <div class="warning-title">⚠ Inferred Activities — Heuristic, Not Measurement</div>
               <p>Everything below this line comes from <b>hand-coded rules</b>
               (e.g., "5–9 AM + 5–15 min duration → shower"), not a trained model.
               The "Confidence" column is a sum of rule matches, <b>not a calibrated probability</b>.</p>
               <p>Read the next charts as a <b>transformation case study</b> — what
               happens when you apply naive heuristics to a stream of plays — rather
               than as ground truth about the listener's day.</p>
               <p><b>Why the rules are this thin:</b> Spotify restricted the
               <code>/audio-features</code> and <code>/artists</code> endpoints for new
               developer apps in 2024, so BPM, energy, valence, and dominant genre are
               stored as NULL. The label engine has only temporal signals (hour,
               duration, skips) to work with.</p>
           </div>
           """,
           unsafe_allow_html=True,
       )
       ```
       Note: the leading `⚠` character is intentional and safe inside HTML markdown rendered by Streamlit (this is browser-rendered, not a Python `print()` — the Windows cp1252 encoding rule from MEMORY.md applies to script stdout, not to HTML strings).

    5. **Sessions** — the existing block at `app.py:255-323` (everything from `section("Sessions")` through the `st.caption(f"Page ... total sessions")` line). After Task 1, this block already uses NumberColumn.

    6. **Activity by Hour** — the `act_hour_df = _activity_by_hour()` block from `app.py:455-484` moves here, immediately after the Sessions block. Add a `st.markdown("<br>", unsafe_allow_html=True)` spacer before it for visual breathing room. Wrap it under its own `section("Activity by Hour")` label so it reads as a distinct sub-zone of the inference area.

    7. **Day Detail** — the existing block at `app.py:327-405` moves to the very end of the layout (just before the footer). After Task 1, the Day Detail's day_sessions table already uses NumberColumn.

    8. **Footer** — the `st.divider()` + two `st.caption(...)` blocks at `app.py:586-597`. The 2024 audio-features note has already been promoted into the warning banner in step 4 above, so:
       - **Keep** the first caption (data pipeline lineage line).
       - **Remove** the second caption (the "Note: audio features (BPM, energy, valence)..." block) — it's now in the warning banner. Avoid duplicate messaging.

    **Critical constraints:**
    - Inside each moved block, do not change a single line of logic, layout, or chart configuration. Only the outer ordering changes.
    - The `<br>` spacer pattern between sections must be preserved (each section already has `st.markdown("<br>", unsafe_allow_html=True)` either before or after — keep that rhythm).
    - All `_kpis()`, `_sessions_page()`, `_activity_by_hour()`, `_plays_by_country()`, etc. calls remain unchanged. Cache decorators are not touched.
    - The `format_sessions_table` helper is not modified.

    After reordering, the file's `# ── N. Section ──` comment headers should be renumbered to match the new order (1. Overview, 2. Listening Patterns, 3. Global Footprint, 4. Warning + Sessions, 5. Activity by Hour, 6. Day Detail). This is cosmetic but keeps the file readable.
  </action>
  <verify>
    <automated>python -c "
src = open('dashboard/app.py', encoding='utf-8').read()
# Section ordering check: locate index of each anchor and verify monotonic order
anchors = [
    ('Overview',        'section(\"Overview\")'),
    ('Listening',       'section(\"Listening Patterns\")'),
    ('Global',          'section(\"Global Footprint\")'),
    ('WarningBanner',   'warning-banner'),
    ('Sessions',        'section(\"Sessions\")'),
    ('ActivityByHour',  'section(\"Activity by Hour\")'),
    ('DayDetail',       'section(\"Day Detail\")'),
]
positions = []
for name, needle in anchors:
    idx = src.find(needle)
    assert idx != -1, f'Missing anchor: {name} ({needle!r})'
    positions.append((name, idx))
for (n1, p1), (n2, p2) in zip(positions, positions[1:]):
    assert p1 < p2, f'Order broken: {n1} ({p1}) should come before {n2} ({p2})'
# Country map block must remain intact
assert 'choropleth' in src and '_COUNTRY_NAMES' in src, 'Country map block damaged'
# Footer audio-features caption must be gone (promoted to banner)
assert 'audio features (BPM, energy, valence)' not in src or src.count('audio features (BPM, energy, valence)') == 0, 'Old footer audio-features caption still present'
# Pipeline lineage caption must remain
assert 'Spotify API -> Supabase' in src, 'Pipeline lineage footer caption removed'
# Compile check
import ast; ast.parse(src)
print('OK — order:', [n for n, _ in positions])
"</automated>
  </verify>
  <done>
    - File parses (`ast.parse` succeeds).
    - The seven section anchors appear in this exact order: Overview → Listening Patterns → Global Footprint → warning-banner → Sessions → Activity by Hour → Day Detail.
    - Country map block (`_COUNTRY_NAMES` + `choropleth` call) is present and unchanged.
    - The "Note: audio features (BPM, energy, valence)..." footer caption is gone (promoted into the warning banner).
    - The "Data pipeline: Spotify API -> Supabase" footer caption is preserved.
    - Running `streamlit run dashboard/app.py` locally renders all sections in the new order without exceptions (manual smoke check).
  </done>
</task>

</tasks>

<verification>
After both tasks complete, perform a smoke verification:

1. **Static check (automated):**
   ```bash
   python -c "import ast; ast.parse(open('dashboard/app.py', encoding='utf-8').read())"
   ```
   Must succeed with no output.

2. **Manual visual check (user, since this is UI work):**
   - Run `streamlit run dashboard/app.py` (or push to Streamlit Cloud).
   - Confirm: 3 KPI cards (no Top Activity), Listening Patterns shows only plays-by-hour + top tracks (no activity-by-hour chart in this section), Global Footprint renders unchanged, amber warning banner appears between Global Footprint and Sessions, Sessions table Confidence column is plain numeric (no progress bar), Activity by Hour appears as its own section after Sessions, Day Detail is last, footer no longer has the audio-features note.

3. **Diff sanity check:**
   ```bash
   git diff --stat dashboard/app.py
   ```
   Only `dashboard/app.py` should be modified. No other files.
</verification>

<success_criteria>
- Single file modified: `dashboard/app.py`.
- All five locked decisions (PIVOT-01 through PIVOT-05) implemented.
- Zero changes to `dashboard/queries.py`, `transformation/`, `ingestion/`, `db/`, schema, or any test file.
- The `_kpis()`, `_activity_by_hour()`, `_plays_by_country()`, `load_*` functions and their cache decorators are untouched.
- Country map block is byte-identical to its prior version (only its position in the file changed).
- Warning banner is visible, amber-styled, and contains both the heuristic-rules framing and the 2024 audio-features-restriction note.
- New section order verified by the automated anchor-position check in Task 2.
- Out of scope (deferred to later phases): new factual queries, plays-by-month, top artists, diversity, dow-hour heatmap, rules panel, sensitivity analysis, adversarial picker, lineage diagram. None of these appear in this plan.
</success_criteria>

<output>
After completion, create `.planning/quick/260429-lyn-phase-1-narrative-pivot-remove-misleadin/260429-lyn-SUMMARY.md` documenting:
- The five PIVOT-* requirements addressed.
- Before/after section order.
- Confirmation that country map and queries layer are untouched.
- Any deviations from the plan (e.g., banner copy adjustments) noted explicitly.
</output>
