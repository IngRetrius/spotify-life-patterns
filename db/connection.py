"""
Shared Supabase connection helpers.

Every pipeline script, the migration runner and the dashboard talked to
the same Supabase instance, each carrying its own copy of the host /
port / user constants. This module centralizes that so credentials and
the pooler endpoint live in exactly one place.

Two entry points:
  - get_connection()  -> raw psycopg2 connection (pipeline scripts)
  - get_engine()      -> SQLAlchemy engine       (dashboard, pandas.read_sql)

Password resolution:
  1. SUPABASE_DB_PASSWORD env var (local .env, GitHub Actions secret)
  2. st.secrets["SUPABASE_DB_PASSWORD"] (Streamlit Cloud)
  3. Raise — no silent fallback to an invalid URL.
"""

import os

import psycopg2
from dotenv import load_dotenv
from sqlalchemy import create_engine

load_dotenv()

# ── Connection constants ──────────────────────────────────────────────────────
# Pooler transaction mode (port 6543) is the endpoint that works on
# Supabase's free tier from both local dev and GitHub Actions. See
# db/migrate.py for the 3-candidate fallback used only at bootstrap.

POOLER_HOST    = "aws-1-us-east-1.pooler.supabase.com"
POOLER_PORT    = 6543
PROJECT_REF    = "ofjjslcrzzllzaiiygya"
POOLER_USER    = f"postgres.{PROJECT_REF}"
DB_NAME        = "postgres"
SSL_MODE       = "require"


def _resolve_password() -> str:
    """
    Read SUPABASE_DB_PASSWORD from whichever source is available.

    Local and CI put it in the environment; Streamlit Cloud exposes it
    only via st.secrets. We probe env first to keep the import cheap
    when streamlit is not installed.
    """
    password = os.getenv("SUPABASE_DB_PASSWORD")
    if password:
        return password

    try:
        import streamlit as st
        password = st.secrets.get("SUPABASE_DB_PASSWORD")
    except Exception:
        password = None

    if not password:
        raise EnvironmentError(
            "SUPABASE_DB_PASSWORD not found. "
            "Set it in .env (local), repo secrets (CI), "
            "or Streamlit Cloud secrets (deploy)."
        )
    return password


def get_connection():
    """Raw psycopg2 connection used by ingestion and transformation scripts."""
    return psycopg2.connect(
        host=POOLER_HOST,
        port=POOLER_PORT,
        user=POOLER_USER,
        password=_resolve_password(),
        dbname=DB_NAME,
        sslmode=SSL_MODE,
    )


def get_engine():
    """
    SQLAlchemy engine for the dashboard. pandas.read_sql and
    st.cache_resource both expect an engine, not a raw connection.
    """
    password = _resolve_password()
    url = (
        f"postgresql+psycopg2://{POOLER_USER}:{password}"
        f"@{POOLER_HOST}:{POOLER_PORT}/{DB_NAME}"
        f"?sslmode={SSL_MODE}"
    )
    return create_engine(url)
