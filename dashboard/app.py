"""
Spotify Life Patterns — Dashboard

Sections:
  1. KPIs    — total plays, listening time, sessions, dominant activity
  2. Sessions — activity breakdown chart + sessions detail table
  3. Patterns — plays by hour of day + top 10 tracks

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

# Allow running from project root: streamlit run dashboard/app.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dashboard.queries import (
    get_engine,
    load_kpis,
    load_sessions,
    load_top_tracks,
    load_plays_by_hour,
    load_activity_counts,
)

# ── Page config ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Spotify Life Patterns",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ───────────────────────────────────────────────────────────────────────

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
</style>
""", unsafe_allow_html=True)

# ── Constants ─────────────────────────────────────────────────────────────────

ACTIVITY_COLORS = {
    "ducha":         "#4C9BE8",
    "gimnasio":      "#E8754C",
    "tareas":        "#4CAF82",
    "aislado":       "#C4A77D",
    "desconocido":   "#9E9E9E",
    "sin etiquetar": "#BDBDBD",
}

DAY_LABELS = {
    0: "Mon", 1: "Tue", 2: "Wed",
    3: "Thu", 4: "Fri", 5: "Sat", 6: "Sun",
}

CHART_LAYOUT = dict(
    template="plotly_white",
    margin=dict(l=0, r=0, t=30, b=0),
    font=dict(family="sans-serif", size=12, color="#495057"),
)

# ── Data loading ──────────────────────────────────────────────────────────────

@st.cache_resource
def _engine():
    """
    Single database engine shared across all queries.
    cache_resource keeps it alive between Streamlit reruns without
    opening a new connection pool each time.
    """
    return get_engine()


@st.cache_data
def _kpis():
    return load_kpis(_engine())


@st.cache_data
def _sessions():
    return load_sessions(_engine())


@st.cache_data
def _top_tracks():
    return load_top_tracks(_engine())


@st.cache_data
def _plays_by_hour():
    return load_plays_by_hour(_engine())


@st.cache_data
def _activity_counts():
    return load_activity_counts(_engine())


# ── Helpers ───────────────────────────────────────────────────────────────────

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


# ── Layout ────────────────────────────────────────────────────────────────────

# Header
st.markdown("## Spotify Life Patterns")
st.markdown(
    "Listening sessions inferred from Spotify history — "
    "activities labeled with heuristic rules.",
)
st.divider()

# ── 1. KPIs ───────────────────────────────────────────────────────────────────

section("Overview")

kpis = _kpis()
hours = kpis["total_minutes"] / 60
time_str = f"{hours:.1f} h" if hours >= 1 else f"{kpis['total_minutes']:.0f} min"

col1, col2, col3, col4 = st.columns(4)
col1.markdown(kpi_card(f"{kpis['total_plays']:,}", "Total Plays"), unsafe_allow_html=True)
col2.markdown(kpi_card(time_str, "Listening Time"), unsafe_allow_html=True)
col3.markdown(kpi_card(str(kpis["total_sessions"]), "Sessions Detected"), unsafe_allow_html=True)
col4.markdown(kpi_card(kpis["top_activity"].capitalize(), "Top Activity", accent=True), unsafe_allow_html=True)

st.markdown("<br>", unsafe_allow_html=True)

# ── 2. Sessions ───────────────────────────────────────────────────────────────

section("Sessions")

col_chart, col_table = st.columns([1, 2], gap="large")

with col_chart:
    act_df = _activity_counts()

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
            yaxis=dict(dtick=1),
            showlegend=False,
        )
        st.plotly_chart(fig_act, use_container_width=True)
    else:
        st.info("No activity labels found. Run label_activities.py first.")

with col_table:
    sessions_df = _sessions()

    if not sessions_df.empty:
        display_df = format_sessions_table(sessions_df)
        st.dataframe(
            display_df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "Confidence": st.column_config.ProgressColumn(
                    "Confidence",
                    min_value=0.0,
                    max_value=1.0,
                    format="%.2f",
                ),
            },
        )
    else:
        st.info("No sessions found. Run build_sessions.py first.")

st.markdown("<br>", unsafe_allow_html=True)

# ── 3. Patterns ───────────────────────────────────────────────────────────────

section("Listening Patterns")

col_hour, col_tracks = st.columns(2, gap="large")

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

with col_tracks:
    tracks_df = _top_tracks()

    if not tracks_df.empty:
        # Truncate long track names for readability
        tracks_df["label"] = tracks_df.apply(
            lambda r: f"{r['track_name'][:30]}  —  {r['artist_name'][:20]}", axis=1
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

# ── Footer ────────────────────────────────────────────────────────────────────

st.divider()
st.caption(
    "Data pipeline: Spotify API -> Supabase (PostgreSQL) -> Streamlit  |  "
    "Activities labeled with heuristic rules (ducha, gimnasio, tareas)"
)
st.caption(
    "Note: audio features (BPM, energy, valence) and dominant genre are "
    "stored as NULL — Spotify restricted /audio-features and /artists "
    "for new developer apps in 2024. Labeling relies on temporal signals only."
)
