# Visualization Layer — Design Decisions

> This document records the reasoning behind every dashboard decision.
> It is the answer to "why did you design the visualization this way?" in an
> interview.

---

## Why Streamlit and not Power BI, Metabase or Grafana

The most common alternatives for data dashboards:

| Tool | Why rejected |
|---|---|
| Power BI / Tableau | Require licenses, not deployable as code, hard to version |
| Metabase / Grafana | Excellent for operations teams, not for engineering portfolios |
| Dash (Plotly) | More flexible, but needs more boilerplate for a similar result |
| Flask + D3.js | Full control, but the development cost is disproportionate here |
| **Streamlit** | Deploys in one line, the code is pure Python, versioned in git like any script |

The key advantage of Streamlit in a Data Engineering portfolio is that **the
dashboard is code**. An interviewer can read `app.py` and understand exactly
how the visualization was built, which queries run, and how data dependencies
are handled.

That is not possible with Power BI or Metabase.

---

## Why `queries.py` is separate from `app.py`

All SQL logic lives in `dashboard/queries.py`. `app.py` only defines the layout.

```
dashboard/
├── app.py       ← what is shown and how (layout, CSS, charts)
└── queries.py   ← what data is loaded and how (SQL, engine, transforms)
```

**Main reason: separation of concerns.**

If the database schema changes (for instance, a new column), only `queries.py`
needs to change. The layout in `app.py` stays untouched.

If we later migrate from Supabase to another engine (BigQuery, Redshift),
we rewrite `queries.py` and `app.py` remains intact.

This also makes queries testable in isolation:
```bash
# Verify all queries work without launching the Streamlit server
python -c "
from dashboard.queries import get_engine, load_kpis, load_sessions
engine = get_engine()
print(load_kpis(engine))
print(load_sessions(engine).shape)
"
```

---

## `@st.cache_resource` vs `@st.cache_data`

Streamlit has two cache types with different purposes:

| Decorator | What for | When it invalidates |
|---|---|---|
| `@st.cache_resource` | Non-serializable objects (connections, ML models) | Only on server restart |
| `@st.cache_data` | Serializable data (DataFrames, dicts, lists) | When arguments change or the TTL expires |

They are used in the dashboard like this:

```python
@st.cache_resource
def _engine():
    # The SQLAlchemy engine manages a connection pool.
    # Creating it once and reusing it avoids opening a new connection
    # on every page interaction.
    return get_engine()

@st.cache_data
def _sessions():
    # The DataFrame is cached in memory.
    # Every user who opens the page gets the same data
    # without issuing an extra query to Supabase.
    return load_sessions(_engine())
```

**Why not use `@st.cache_data` for the engine:**
The engine holds a pool of live connections that cannot be serialized (pickled).
Attempting to do so raises an error. `@st.cache_resource` is designed exactly
for this.

**Why not use `@st.cache_resource` for DataFrames:**
`@st.cache_resource` shares the object across all users without copying it.
If a function modified the DataFrame (not the case here), every user would see
the modified data. `@st.cache_data` returns a per-user copy.

---

## Why SQLAlchemy and not raw psycopg2

```python
# Form that raises a warning in pandas >= 2.0:
df = pd.read_sql(query, psycopg2_conn)

# Correct form:
df = pd.read_sql(query, sqlalchemy_engine)
```

Starting with pandas 2.0, `read_sql` requires a SQLAlchemy engine or a
connection URL. Passing a raw psycopg2 connection raises a `UserWarning` and
will stop working in future pandas versions.

SQLAlchemy also manages a **connection pool** automatically: instead of
opening and closing a TCP connection per query, it reuses existing ones.
With the Supabase pooler (transaction mode, port 6543) this noticeably
reduces latency.

---

## The `_get_password()` pattern — two credential sources

The dashboard must work in two environments with different ways of passing
secrets:

| Environment | How credentials are read |
|---|---|
| Local | `python-dotenv` loads `.env` as environment variables → `os.getenv()` |
| Streamlit Cloud | Dashboard secrets are accessed via `st.secrets`, NOT as env vars |

```python
def _get_password() -> str:
    # 1. Try as an environment variable (works locally with .env)
    password = os.getenv("SUPABASE_DB_PASSWORD")

    # 2. If absent, try Streamlit Cloud secrets
    if not password:
        try:
            import streamlit as st
            password = st.secrets.get("SUPABASE_DB_PASSWORD")
        except Exception:
            pass

    # 3. If missing everywhere, fail with a clear message
    if not password:
        raise EnvironmentError(
            "SUPABASE_DB_PASSWORD not found. "
            "Set it in .env (local) or Streamlit Cloud secrets (deploy)."
        )
    return password
```

This pattern avoids having two versions of the connection file (one for local,
one for deploy) and makes the source-priority order explicit.

---

## Why timezone conversion happens in SQL and not in Python

```sql
-- In queries.py:
s.start_time AT TIME ZONE 'America/Bogota' AS start_time
```

The alternative would be to fetch the timestamp in UTC and convert it in Python:
```python
df["start_time"] = df["start_time"].dt.tz_convert("America/Bogota")
```

SQL was chosen for two reasons:

1. **Data arrives already in the correct timezone.** The DataFrame does not
   need to be manipulated after loading — what you read is what the user sees.

2. **Centralizes presentation logic in one place.** Any query that exposes
   timestamps to the user converts them in the same layer (SQL), instead of
   relying on every Python snippet to remember the conversion.

General rule: always store in UTC, convert to the user's timezone at the
presentation layer. Here that layer is the dashboard's SQL query.

---

## Why Plotly and not Altair (Streamlit's default)

Streamlit ships Altair as its integrated visualization. Plotly was chosen
because:

| Feature | Altair | Plotly |
|---|---|---|
| Interactivity (hover, zoom, pan) | Limited | Full |
| Tooltip customization | Declarative, verbose | Direct with `hovertemplate` |
| 3D charts and maps | No | Yes (useful in future phases) |
| Ecosystem | Vega-Altair | Broad, well documented |

For a portfolio showing behavioral patterns, Plotly's interactivity lets
visitors explore the data (e.g. hover a session and see its exact duration),
which makes the presentation more convincing.

---

## Why there is no refresh button

The dashboard has no "Refresh" button. Data is loaded when the page opens
and served from cache until the server restarts.

**Justification for this case:**
- The pipeline runs every 6 hours via GitHub Actions. Data does not change in
  real time.
- Adding a refresh button would require calling `st.cache_data.clear()`, which
  invalidates the cache for every user at once.
- For the current volume (4 sessions), the latency of a direct query is
  minimal, but the caching pattern is the right one for scaling to hundreds
  of sessions without flooding the Supabase pooler with redundant requests.

When the dataset grows significantly, a `ttl` parameter can be added to the
cache decorator:
```python
@st.cache_data(ttl=3600)  # auto-invalidates every hour
def _sessions():
    return load_sessions(_engine())
```

---

## Why AT TIME ZONE produces `timestamp without time zone` in pandas

A relevant technical detail: when PostgreSQL applies `AT TIME ZONE` to a
`TIMESTAMPTZ`, the result is a `timestamp without time zone` (the offset has
already been applied, the zone is no longer embedded in the value).

Pandas reads this as a naive datetime (no tzinfo). That is why in `app.py`:
```python
pd.to_datetime(df["start_time"]).dt.strftime("%b %d, %Y  %H:%M")
```
There is no need to call `.dt.tz_localize()` or `.dt.tz_convert()` — the value
is already in Bogotá time, even without an explicit offset.

---

## Executive summary for interviews

Four principles applied in this layer:

1. **UI / data separation**
   `queries.py` holds all SQL. `app.py` only defines the layout.
   Changing the schema does not require touching the presentation, and vice versa.

2. **Cache per object type**
   `@st.cache_resource` for the connection pool (non-serializable),
   `@st.cache_data` for DataFrames (serializable, copied per user).

3. **Environment-agnostic credentials**
   A single `_get_password()` works locally (dotenv) and in Streamlit Cloud
   (st.secrets) without needing two versions of the connection file.

4. **Timezone at the correct layer**
   UTC in the database, conversion to the user's timezone in the SQL query.
   The DataFrame that arrives in Python is already in local time, with no
   further transformations.

> Short interview answer:
> "I separated queries from UI so the schema can evolve without touching the
> layout. I use cache_resource for the engine (connection pool) and cache_data
> for DataFrames, which is the distinction Streamlit expects. Secrets come
> from dotenv locally and st.secrets in production — one codebase for two
> environments."
