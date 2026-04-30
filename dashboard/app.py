"""
Spotify Life Patterns - Dashboard

Narrative structure (3 zones):
  1. Facts        - KPIs, Listening Patterns, Global Footprint (raw Spotify data)
  2. Inferences   - Sessions + Activity by Hour (heuristic labels, NOT measurement)
  3. Drill-down   - Day Detail (mix of factual tracks + inferred sessions)

Architecture notes:
  - queries.py holds all SQL logic; app.py is pure layout
  - @st.cache_resource: database engine (one pool, reused across reruns)
  - @st.cache_data: query results (cached on page load, no refresh button needed)
  - All timestamps converted to America/Bogota at the SQL layer
"""

import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import sys
import os
from datetime import timedelta

# Allow running from project root: streamlit run dashboard/app.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.queries import (
    get_engine,
    load_kpis,
    load_sessions,
    count_sessions,
    load_sessions_for_day,
    load_top_tracks,
    load_plays_by_hour,
    load_activity_counts,
    load_plays_for_day,
    load_available_dates,
    load_activity_by_hour,
    load_plays_by_country,
    load_plays_by_month,
    load_top_artists,
    load_diversity_by_month,
    load_dow_hour_heatmap,
    load_confidence_distribution,
    load_random_sessions_by_label,
    load_session_tracks,
)

# -- Page config --------------------------------------------------------------

st.set_page_config(
    page_title="Spotify Life Patterns",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# -- CSS ----------------------------------------------------------------------

st.markdown("""
<style>
    /* Remove default top padding */
    .block-container { padding-top: 2rem; }

    /* Section headers */
    .section-label {
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: #6c757d;
        border-bottom: 2px solid #1DB954;
        padding-bottom: 4px;
        margin-bottom: 1rem;
    }

    /* KPI cards */
    .kpi-card {
        background: #f8f9fa;
        border-radius: 10px;
        padding: 1.2rem 1.5rem;
        border: 1px solid #e9ecef;
    }
    .kpi-value {
        font-size: 2rem;
        font-weight: 700;
        color: #212529;
        line-height: 1.1;
    }
    .kpi-label {
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #adb5bd;
        margin-top: 4px;
    }
    .kpi-accent { color: #1DB954; }

    /* Warning banner: introduces the inference zone (heuristic, not measurement) */
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
    .warning-banner code {
        background: #fff1c4;
        padding: 1px 5px;
        border-radius: 3px;
        font-size: 0.88em;
    }
</style>
""", unsafe_allow_html=True)

# -- Constants ----------------------------------------------------------------

ACTIVITY_COLORS = {
    "shower":    "#4C9BE8",
    "gym":       "#E8754C",
    "tasks":     "#4CAF82",
    "casual":    "#C4A77D",
    "unknown":   "#9E9E9E",
    "unlabeled": "#BDBDBD",
}

DAY_LABELS = {
    0: "Mon", 1: "Tue", 2: "Wed",
    3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun",
}

# Y-axis labels for the dow x hour heatmap (Monday=0, matches the SQL
# normalization in load_dow_hour_heatmap).
DOW_LABELS_MON0 = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

CHART_LAYOUT = dict(
    template="plotly_white",
    margin=dict(l=0, r=0, t=30, b=0),
    font=dict(family="sans-serif", size=12, color="#495057"),
)

# -- Data loading -------------------------------------------------------------

@st.cache_resource
def _engine():
    """
    Single database engine shared across all queries.
    cache_resource keeps it alive between Streamlit reruns without
    opening a new connection pool each time.
    """
    return get_engine()


@st.cache_data(ttl=timedelta(hours=3))
def _kpis():
    return load_kpis(_engine())


SESSIONS_PAGE_SIZE = 50


@st.cache_data(ttl=timedelta(hours=3))
def _sessions_page(page: int, page_size: int = SESSIONS_PAGE_SIZE):
    offset = (page - 1) * page_size
    return load_sessions(_engine(), limit=page_size, offset=offset)


@st.cache_data(ttl=timedelta(hours=3))
def _sessions_count() -> int:
    return count_sessions(_engine())


@st.cache_data(ttl=timedelta(hours=3))
def _sessions_for_day(day):
    return load_sessions_for_day(_engine(), day)


@st.cache_data(ttl=timedelta(hours=3))
def _top_tracks():
    return load_top_tracks(_engine())


@st.cache_data(ttl=timedelta(hours=3))
def _plays_by_hour():
    return load_plays_by_hour(_engine())


@st.cache_data(ttl=timedelta(hours=3))
def _activity_counts():
    return load_activity_counts(_engine())


@st.cache_data(ttl=timedelta(hours=3))
def _available_dates():
    return load_available_dates(_engine())


@st.cache_data(ttl=timedelta(hours=3))
def _activity_by_hour():
    return load_activity_by_hour(_engine())


@st.cache_data(ttl=timedelta(hours=3))
def _plays_for_day(day):
    return load_plays_for_day(_engine(), day)


@st.cache_data(ttl=timedelta(hours=3))
def _plays_by_country():
    return load_plays_by_country(_engine())


@st.cache_data(ttl=timedelta(hours=3))
def _plays_by_month():
    return load_plays_by_month(_engine())


@st.cache_data(ttl=timedelta(hours=3))
def _top_artists():
    return load_top_artists(_engine())


@st.cache_data(ttl=timedelta(hours=3))
def _diversity_by_month():
    return load_diversity_by_month(_engine())


@st.cache_data(ttl=timedelta(hours=3))
def _dow_hour_heatmap():
    return load_dow_hour_heatmap(_engine())


@st.cache_data(ttl=timedelta(hours=3))
def _confidence_distribution():
    return load_confidence_distribution(_engine())


# -- Helpers ------------------------------------------------------------------

def section(title: str) -> None:
    """Renders a styled section header."""
    st.markdown(f'<div class="section-label">{title}</div>', unsafe_allow_html=True)


def kpi_card(value: str, label: str, accent: bool = False) -> str:
    val_class = "kpi-value kpi-accent" if accent else "kpi-value"
    return f"""
    <div class="kpi-card">
        <div class="{val_class}">{value}</div>
        <div class="kpi-label">{label}</div>
    </div>
    """


def format_sessions_table(df: pd.DataFrame) -> pd.DataFrame:
    """Prepares the sessions DataFrame for display."""
    out = df.copy()
    out["start_time"] = pd.to_datetime(out["start_time"]).dt.strftime("%b %d, %Y  %H:%M")
    out["day_of_week"] = out["day_of_week"].map(DAY_LABELS)
    out["duration_minutes"] = out["duration_minutes"].round(1)
    out["confidence_score"] = out["confidence_score"].round(2)
    return out[[
        "start_time", "duration_minutes", "hour_of_day",
        "day_of_week", "n_tracks", "n_skips",
        "activity_label", "confidence_score",
    ]].rename(columns={
        "start_time":       "Date & Time",
        "duration_minutes": "Duration (min)",
        "hour_of_day":      "Hour",
        "day_of_week":      "Day",
        "n_tracks":         "Tracks",
        "n_skips":          "Skips",
        "activity_label":   "Activity",
        "confidence_score": "Confidence",
    })


@st.cache_resource(show_spinner=False)
def _rules_source() -> str:
    """
    Read transformation/label_activities.py and slice the meaningful
    portion (constants + rule functions + RULES dict) so the dashboard
    can render the actual code in the 'Rules' panel.

    Cached as a resource since the file changes only when the labeling
    engine is updated — and the dashboard is restarted on deploy.
    """
    label_path = os.path.join(
        os.path.dirname(__file__), "..", "transformation", "label_activities.py"
    )
    try:
        with open(label_path, "r", encoding="utf-8") as f:
            full = f.read()
    except FileNotFoundError:
        return "# Source file not found: transformation/label_activities.py"

    # Slice from the first hour-window section through the RULES dict.
    start_marker = "# ── Hour windows"  # box-drawing char already in source
    end_marker = "def classify_session"
    start = full.find(start_marker)
    end = full.find(end_marker)
    if start == -1 or end == -1:
        # Fall back to a plain anchor (the box-drawing char varies).
        start = full.find("SHOWER_HOURS")
        end = full.find("def classify_session")
        if start == -1 or end == -1:
            return full  # last resort: show the whole file

    return full[start:end].rstrip()


# Column config shared by both sessions tables: plain numeric Confidence,
# explicitly NOT a probability bar.
SESSIONS_COLUMN_CONFIG = {
    "Confidence": st.column_config.NumberColumn(
        "Confidence",
        format="%.2f",
        help="Heuristic rule-match score, not a calibrated probability.",
    ),
}


# -- Layout -------------------------------------------------------------------

# Header
st.markdown("## Spotify Life Patterns")
st.markdown(
    "Honest listening data + a case study in how naive transformations create false confidence."
)
st.divider()

# -- 1. Overview (FACTS) ------------------------------------------------------

section("Overview")

kpis = _kpis()
hours = kpis["total_minutes"] / 60
time_str = f"{hours:.1f} h" if hours >= 1 else f"{kpis['total_minutes']:.0f} min"

col1, col2, col3 = st.columns(3)
col1.markdown(kpi_card(f"{kpis['total_plays']:,}", "Total Plays"), unsafe_allow_html=True)
col2.markdown(kpi_card(time_str, "Listening Time"), unsafe_allow_html=True)
col3.markdown(kpi_card(str(kpis["total_sessions"]), "Sessions Detected"), unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# -- 2. Listening Patterns (FACTS) --------------------------------------------
# Four-row layout:
#   Row 1: Plays by Month (full width, hero chart)
#   Row 2: Top Tracks | Top Artists
#   Row 3: Plays by Hour | Diversity by Month
#   Row 4: Day-of-week x Hour heatmap (full width)

section("Listening Patterns")

# -- Row 1: Plays by Month (hero) --
month_df = _plays_by_month()

if not month_df.empty:
    fig_month = px.bar(
        month_df,
        x="month",
        y="plays",
        labels={"month": "Month (Bogota)", "plays": "Plays"},
        title="Plays by Month",
        color_discrete_sequence=["#1DB954"],
        custom_data=["minutes"],
    )
    fig_month.update_layout(**CHART_LAYOUT)
    fig_month.update_traces(
        hovertemplate=(
            "<b>%{x|%b %Y}</b><br>"
            "Plays: %{y:,}<br>"
            "Minutes listened: %{customdata[0]:,.0f}<extra></extra>"
        )
    )
    st.plotly_chart(fig_month, use_container_width=True)
else:
    st.info("No play data yet.")

# -- Row 2: Top Tracks | Top Artists --
col_tracks, col_artists = st.columns(2, gap="large")

with col_tracks:
    tracks_df = _top_tracks()

    if not tracks_df.empty:
        # Truncate long track names for readability
        tracks_df["label"] = tracks_df.apply(
            lambda r: f"{r['track_name'][:30]}  -  {r['artist_name'][:20]}", axis=1
        )

        fig_tracks = px.bar(
            tracks_df.sort_values("play_count"),
            x="play_count",
            y="label",
            orientation="h",
            labels={"play_count": "Plays", "label": ""},
            title="Top 10 Tracks",
            color_discrete_sequence=["#4C9BE8"],
        )
        fig_tracks.update_layout(**CHART_LAYOUT)
        fig_tracks.update_traces(
            hovertemplate="<b>%{y}</b><br>Plays: %{x}<extra></extra>"
        )
        st.plotly_chart(fig_tracks, use_container_width=True)
    else:
        st.info("No play data found.")

with col_artists:
    artists_df = _top_artists()

    if not artists_df.empty:
        artists_df["label"] = artists_df["artist_name"].str.slice(0, 40)

        fig_artists = px.bar(
            artists_df.sort_values("play_count"),
            x="play_count",
            y="label",
            orientation="h",
            labels={"play_count": "Plays", "label": ""},
            title="Top 10 Artists",
            color_discrete_sequence=["#E8754C"],
        )
        fig_artists.update_layout(**CHART_LAYOUT)
        fig_artists.update_traces(
            hovertemplate="<b>%{y}</b><br>Plays: %{x}<extra></extra>"
        )
        st.plotly_chart(fig_artists, use_container_width=True)
    else:
        st.info("No artist data found.")

# -- Row 3: Plays by Hour | Diversity by Month --
col_hour, col_diversity = st.columns(2, gap="large")

with col_hour:
    hour_df = _plays_by_hour()

    fig_hour = px.bar(
        hour_df,
        x="hour",
        y="plays",
        labels={"hour": "Hour of Day (Bogota)", "plays": "Plays"},
        title="Plays by Hour of Day",
        color_discrete_sequence=["#1DB954"],
    )
    fig_hour.update_layout(**CHART_LAYOUT)
    fig_hour.update_traces(hovertemplate="<b>%{x}:00</b><br>Plays: %{y}<extra></extra>")
    fig_hour.update_xaxes(tickvals=list(range(0, 24, 2)))
    st.plotly_chart(fig_hour, use_container_width=True)

with col_diversity:
    div_df = _diversity_by_month()

    if not div_df.empty:
        fig_div = go.Figure()
        fig_div.add_trace(go.Scatter(
            x=div_df["month"],
            y=div_df["unique_tracks"],
            mode="lines+markers",
            name="Unique tracks",
            line=dict(color="#1DB954", width=2),
            marker=dict(size=6),
            hovertemplate="<b>%{x|%b %Y}</b><br>Unique tracks: %{y}<extra></extra>",
        ))
        fig_div.add_trace(go.Scatter(
            x=div_df["month"],
            y=div_df["unique_artists"],
            mode="lines+markers",
            name="Unique artists",
            line=dict(color="#4C9BE8", width=2),
            marker=dict(size=6),
            hovertemplate="<b>%{x|%b %Y}</b><br>Unique artists: %{y}<extra></extra>",
        ))
        fig_div.update_layout(
            **CHART_LAYOUT,
            title="Diversity by Month",
            xaxis_title="Month (Bogota)",
            yaxis_title="Count",
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1,
            ),
        )
        st.plotly_chart(fig_div, use_container_width=True)
    else:
        st.info("No diversity data yet.")

# -- Row 4: Day-of-week x Hour heatmap (full width) --
heat_df = _dow_hour_heatmap()

if not heat_df.empty:
    # Pivot from long to 7x24 matrix; rows = dow (Mon=0..Sun=6), cols = hour.
    heat_matrix = (
        heat_df
        .pivot(index="dow", columns="hour", values="plays")
        .reindex(index=range(7), columns=range(24))
        .fillna(0)
        .astype(int)
    )

    fig_heat = go.Figure(go.Heatmap(
        z=heat_matrix.values,
        x=list(range(24)),
        y=DOW_LABELS_MON0,
        colorscale="Greens",
        hovertemplate=(
            "<b>%{y} %{x}:00</b><br>"
            "Plays: %{z}<extra></extra>"
        ),
        colorbar=dict(title="Plays", thickness=12, len=0.7),
    ))
    fig_heat.update_layout(
        **CHART_LAYOUT,
        title="Day of Week x Hour of Day",
        xaxis_title="Hour (Bogota)",
        yaxis_title=None,
        xaxis=dict(tickvals=list(range(0, 24, 2)), tickmode="array"),
        yaxis=dict(autorange="reversed"),  # Mon at the top
    )
    st.plotly_chart(fig_heat, use_container_width=True)

# -- 3. Global Footprint (FACTS) ----------------------------------------------

st.markdown("<br>", unsafe_allow_html=True)
section("Global Footprint")

# ISO alpha-2 -> country name mapping for the countries in the dataset
_COUNTRY_NAMES = {
    "CO": "Colombia",
    "US": "United States",
    "TR": "Turkey",
    "ES": "Spain",
    "DE": "Germany",
    "PA": "Panama",
    "IT": "Italy",
    "MX": "Mexico",
    "FR": "France",
    "PT": "Portugal",
    "NL": "Netherlands",
}

country_df = _plays_by_country()

if not country_df.empty:
    country_df["country_name"] = country_df["country_code"].map(
        lambda c: _COUNTRY_NAMES.get(c, c)
    )

    col_map, col_bar = st.columns([3, 2], gap="large")

    with col_map:
        fig_map = px.choropleth(
            country_df,
            locations="country_name",
            locationmode="country names",
            color="plays",
            hover_name="country_name",
            custom_data=["plays", "minutes_played"],
            color_continuous_scale=[
                [0.0,  "#e8f5e9"],
                [0.15, "#a5d6a7"],
                [0.4,  "#4CAF50"],
                [0.7,  "#2E7D32"],
                [1.0,  "#1B5E20"],
            ],
            title="Plays by Country",
        )
        fig_map.update_layout(
            **CHART_LAYOUT,
            geo=dict(
                showframe=False,
                showcoastlines=True,
                coastlinecolor="#dee2e6",
                showland=True,
                landcolor="#f8f9fa",
                showocean=True,
                oceancolor="#e9ecef",
                projection_type="natural earth",
            ),
            coloraxis_colorbar=dict(
                title="Plays",
                thickness=12,
                len=0.6,
            ),
        )
        fig_map.update_traces(
            hovertemplate=(
                "<b>%{hovertext}</b><br>"
                "Plays: %{customdata[0]:,}<br>"
                "Minutes listened: %{customdata[1]:,.0f}<extra></extra>"
            )
        )
        st.plotly_chart(fig_map, use_container_width=True)

    with col_bar:
        fig_country = px.bar(
            country_df.sort_values("plays"),
            x="plays",
            y="country_name",
            orientation="h",
            text="plays",
            color="plays",
            color_continuous_scale=[
                [0.0, "#a5d6a7"],
                [1.0, "#1B5E20"],
            ],
            labels={"plays": "Plays", "country_name": ""},
            title="Plays by Country",
        )
        fig_country.update_layout(
            **CHART_LAYOUT,
            showlegend=False,
            coloraxis_showscale=False,
        )
        fig_country.update_traces(
            texttemplate="%{text:,}",
            textposition="outside",
            hovertemplate="<b>%{y}</b><br>Plays: %{x:,}<extra></extra>",
        )
        st.plotly_chart(fig_country, use_container_width=True)

# -- 4. Warning banner (transition into INFERENCE zone) -----------------------

st.markdown("<br>", unsafe_allow_html=True)
st.markdown(
    """
    <div class="warning-banner">
        <div class="warning-title">&#9888; Inferred Activities &mdash; Heuristic, Not Measurement</div>
        <p>Everything below this line comes from <b>hand-coded rules</b>
        (e.g., "5&ndash;9 AM + 5&ndash;15 min duration &rarr; shower"), not a trained model.
        The "Confidence" column is a sum of rule matches, <b>not a calibrated probability</b>.</p>
        <p>Read the next charts as a <b>transformation case study</b> &mdash; what
        happens when you apply naive heuristics to a stream of plays &mdash; rather
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

# -- 4a. Residual KPI: "What I cannot tell you" -------------------------------
# Computed from the existing _activity_counts() data — no new query needed.
# Promotes the most honest result of the project (the share of sessions
# whose patterns the rules could NOT confidently classify) to the top of
# the inference zone.

_residual_df = _activity_counts()
_residual_df = _residual_df[_residual_df["activity_label"].notna() & (_residual_df["activity_label"] != "")]

if not _residual_df.empty:
    _total = int(_residual_df["sessions"].sum())
    _residual_mask = _residual_df["activity_label"].isin(["casual", "unknown", "unlabeled"])
    _residual_n = int(_residual_df.loc[_residual_mask, "sessions"].sum())
    _residual_pct = (100.0 * _residual_n / _total) if _total else 0.0

    rk1, rk2, rk3 = st.columns([1, 1, 2], gap="large")
    rk1.metric(
        "Sessions without a clear pattern",
        f"{_residual_pct:.0f}%",
        help="Share of sessions labeled 'casual' or 'unknown' — the rules could not tie them to a routine.",
    )
    rk2.metric(
        "Sessions classified",
        f"{_total - _residual_n:,} / {_total:,}",
        help="How many of your sessions the heuristic labeled as one of shower / gym / tasks.",
    )
    rk3.markdown(
        """
        <div class="warning-banner" style="background:#f3f6f9; border-left-color:#6c757d; color:#495057;">
            <p style="margin:0;">A high residual is the most honest result of this project.
            It means the rules <b>refused to guess</b> on sessions that did not match a known
            duration / hour pattern — preferable to a confidently wrong label.</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

# -- 4b. The Rules panel ------------------------------------------------------
# Renders the actual source of transformation/label_activities.py so the
# reader can see exactly what 'shower' or 'gym' means before reading any
# of the inferred charts below.

with st.expander("Show the labeling rules — see exactly what 'gym' or 'shower' means", expanded=False):
    st.markdown(
        "These are the **actual rules** that produced every label below. "
        "No machine learning, no probability — just hand-coded thresholds on duration, "
        "hour-of-day, and skip count."
    )
    st.code(_rules_source(), language="python")

st.markdown("<br>", unsafe_allow_html=True)

# -- 5. Sessions (INFERENCES) -------------------------------------------------

section("Sessions")

col_chart, col_table = st.columns([1, 2], gap="large")

with col_chart:
    act_df = _activity_counts()

    # Drop NULL/empty activity_label rows that GROUP BY would otherwise render
    # as a tiny ghost bar pinned to the y-axis.
    act_df = act_df[act_df["activity_label"].notna() & (act_df["activity_label"] != "")]

    if not act_df.empty:
        # Map colors; default grey for any unknown label
        bar_colors = [ACTIVITY_COLORS.get(lbl, "#9E9E9E") for lbl in act_df["activity_label"]]

        fig_act = go.Figure(go.Bar(
            x=act_df["activity_label"].str.capitalize(),
            y=act_df["sessions"],
            marker_color=bar_colors,
            text=act_df["sessions"],
            textposition="outside",
            hovertemplate=(
                "<b>%{x}</b><br>"
                "Sessions: %{y}<br>"
                "Avg confidence: %{customdata:.2f}<extra></extra>"
            ),
            customdata=act_df["avg_confidence"],
        ))
        fig_act.update_layout(
            **CHART_LAYOUT,
            title="Sessions by Activity",
            xaxis_title=None,
            yaxis_title="Sessions",
            showlegend=False,
        )
        st.plotly_chart(fig_act, use_container_width=True)
    else:
        st.info("No activity labels found. Run label_activities.py first.")

with col_table:
    total_sessions = _sessions_count()

    if total_sessions == 0:
        st.info("No sessions found. Run build_sessions.py first.")
    else:
        total_pages = max(1, (total_sessions + SESSIONS_PAGE_SIZE - 1) // SESSIONS_PAGE_SIZE)
        page = st.number_input(
            "Page",
            min_value=1,
            max_value=total_pages,
            value=1,
            step=1,
            help=f"{total_sessions} sessions total, {SESSIONS_PAGE_SIZE} per page.",
        )
        sessions_df = _sessions_page(int(page), SESSIONS_PAGE_SIZE)
        display_df = format_sessions_table(sessions_df)
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config=SESSIONS_COLUMN_CONFIG,
        )
        st.caption(f"Page {int(page)} of {total_pages} - {total_sessions} total sessions")

# -- 5b. Confidence-score distribution (INFERENCES) ---------------------------
# Histogram of the raw confidence_score values. Designed to make visible
# that the score clusters at predictable values (0.4, 0.5, 0.7) because
# it is a sum of rule matches — not a calibrated probability.

st.markdown("<br>", unsafe_allow_html=True)
section("Confidence Distribution")

col_hist, col_explain = st.columns([2, 1], gap="large")

with col_hist:
    conf_df = _confidence_distribution()

    if not conf_df.empty:
        fig_conf = px.histogram(
            conf_df,
            x="confidence_score",
            nbins=20,
            title="Confidence-score distribution across all labeled sessions",
            color_discrete_sequence=["#f5a623"],
        )
        fig_conf.update_layout(
            **CHART_LAYOUT,
            xaxis_title="Confidence score",
            yaxis_title="Sessions",
            bargap=0.05,
        )
        fig_conf.update_traces(
            hovertemplate="<b>Score: %{x:.2f}</b><br>Sessions: %{y}<extra></extra>"
        )
        st.plotly_chart(fig_conf, use_container_width=True)
    else:
        st.info("No confidence scores available yet.")

with col_explain:
    st.markdown(
        """
        **This is not a probability.**

        A score of `0.65` does **not** mean *"I am 65% sure this is a shower."*
        It means roughly **3 of 5 conditions** matched (e.g. duration band + correct hour
        + zero skips).

        Notice the clusters at `0.4`, `0.5`, `0.7` — those are the discrete sums
        the rules can produce. A real probability distribution would be smooth.
        """
    )

# -- 6. Activity by Hour (INFERENCES) -----------------------------------------

st.markdown("<br>", unsafe_allow_html=True)
section("Activity by Hour")

act_hour_df = _activity_by_hour()

if not act_hour_df.empty:
    fig_act_hour = px.bar(
        act_hour_df,
        x="hour",
        y="sessions",
        color="activity_label",
        color_discrete_map=ACTIVITY_COLORS,
        barmode="stack",
        labels={
            "hour":           "Hour of Day (Bogota)",
            "sessions":       "Sessions",
            "activity_label": "Activity",
        },
        title="Activity by Hour of Day",
    )
    fig_act_hour.update_layout(
        **CHART_LAYOUT,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
        ),
    )
    fig_act_hour.update_xaxes(tickvals=list(range(0, 24, 2)))
    fig_act_hour.for_each_trace(lambda t: t.update(name=t.name.capitalize()))
    st.plotly_chart(fig_act_hour, use_container_width=True)

# -- 6b. Adversarial picker (INFERENCES) --------------------------------------
# Pick a label, surface 3 random sessions of that label and list their
# tracks. One contradictory example (a 'gym' session full of ballads;
# a 'shower' session that turns out to be a podcast) does more for the
# narrative than a paragraph of disclaimers.

st.markdown("<br>", unsafe_allow_html=True)
section("Adversarial Examples")

st.markdown(
    "Pick a label below to surface **three random sessions** that the rules tagged "
    "with it — and the tracks that actually played. The most honest way to test a "
    "heuristic is to look at what it caught."
)

# Build the label list from existing _activity_counts (ordered by count desc).
_picker_df = _activity_counts()
_picker_df = _picker_df[_picker_df["activity_label"].notna() & (_picker_df["activity_label"] != "")]
_label_options = _picker_df["activity_label"].tolist()

if _label_options:
    col_pick, col_sample = st.columns([1, 3], gap="large")

    with col_pick:
        picked_label = st.selectbox(
            "Activity label",
            _label_options,
            format_func=lambda s: s.capitalize(),
        )
        st.caption(
            f"{int(_picker_df.loc[_picker_df['activity_label'] == picked_label, 'sessions'].iloc[0]):,} "
            f"sessions tagged as **{picked_label}**."
        )
        roll = st.button("Roll 3 random sessions", use_container_width=True)

    with col_sample:
        # Use a session_state seed so the same selection survives reruns
        # until the user explicitly rolls new ones.
        if "adv_seed" not in st.session_state:
            st.session_state.adv_seed = 0
        if roll:
            st.session_state.adv_seed += 1

        # Cache key on (label, seed) so each roll is fresh but stable until rerolled.
        @st.cache_data(ttl=timedelta(minutes=10))
        def _adv_sessions(label: str, seed: int) -> pd.DataFrame:
            return load_random_sessions_by_label(_engine(), label, n=3)

        sample_df = _adv_sessions(picked_label, st.session_state.adv_seed)

        if sample_df.empty:
            st.info(f"No sessions tagged as '{picked_label}' yet.")
        else:
            for _, sess in sample_df.iterrows():
                start = pd.to_datetime(sess["start_time"]).strftime("%b %d, %Y at %H:%M")
                st.markdown(
                    f"**{start}** &middot; "
                    f"{sess['duration_minutes']:.1f} min &middot; "
                    f"{int(sess['n_tracks'])} tracks &middot; "
                    f"confidence `{float(sess['confidence_score']):.2f}`",
                    unsafe_allow_html=True,
                )

                tracks = load_session_tracks(_engine(), sess["session_id"])
                if tracks.empty:
                    st.caption("(no tracks recorded for this session window)")
                else:
                    tracks_view = tracks.copy()
                    tracks_view["played_at_local"] = pd.to_datetime(
                        tracks_view["played_at_local"]
                    ).dt.strftime("%H:%M")
                    tracks_view = tracks_view.rename(columns={
                        "played_at_local":  "Time",
                        "track_name":       "Track",
                        "artist_name":      "Artist",
                        "duration_minutes": "Duration (min)",
                    })
                    st.dataframe(tracks_view, use_container_width=True, hide_index=True)

                st.markdown("<hr style='margin:0.6rem 0;border:0;border-top:1px solid #e9ecef;'/>", unsafe_allow_html=True)

# -- 7. Day Detail (drill-down: factual tracks + inferred sessions) -----------

st.markdown("<br>", unsafe_allow_html=True)
section("Day Detail")

dates_df = _available_dates()

if dates_df.empty:
    st.info("No play data available yet.")
else:
    available = pd.to_datetime(dates_df["day"]).dt.date
    min_day, max_day = available.min(), available.max()
    default_day = max_day  # open on the most recent day with data

    col_picker, col_summary = st.columns([1, 3], gap="large")

    with col_picker:
        selected_day = st.date_input(
            "Pick a day",
            value=default_day,
            min_value=min_day,
            max_value=max_day,
            help="Only days with listening activity are in range.",
        )
        has_data = selected_day in set(available)
        if not has_data:
            st.caption(f"No plays on {selected_day}. Try another date.")

    with col_summary:
        if has_data:
            day_plays = _plays_for_day(selected_day)

            day_sessions = _sessions_for_day(selected_day)

            n_plays = len(day_plays)
            total_min = float(day_plays["duration_minutes"].sum())
            n_sessions = len(day_sessions)
            top_activity = (
                day_sessions["activity_label"].mode().iloc[0]
                if not day_sessions.empty else "-"
            )

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Plays",          n_plays)
            m2.metric("Minutes",        f"{total_min:.0f}")
            m3.metric("Sessions",       n_sessions)
            m4.metric("Top activity",   top_activity.capitalize())

    if has_data:
        if not day_sessions.empty:
            st.markdown("**Sessions that day**")
            day_display = format_sessions_table(day_sessions)
            st.dataframe(
                day_display,
                use_container_width=True,
                hide_index=True,
                column_config=SESSIONS_COLUMN_CONFIG,
            )

        st.markdown("**Tracks played that day**")
        tracks_view = day_plays.copy()
        tracks_view["played_at_local"] = pd.to_datetime(
            tracks_view["played_at_local"]
        ).dt.strftime("%H:%M")
        tracks_view = tracks_view.rename(columns={
            "played_at_local":  "Time",
            "track_name":       "Track",
            "artist_name":      "Artist",
            "duration_minutes": "Duration (min)",
        })
        st.dataframe(tracks_view, use_container_width=True, hide_index=True)

# -- Footer -------------------------------------------------------------------

st.divider()
st.caption(
    "Data pipeline: Spotify API -> Supabase (PostgreSQL) -> Streamlit  |  "
    "Activities labeled with heuristic rules (shower, gym, tasks, casual)"
)
