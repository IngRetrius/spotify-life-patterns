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
