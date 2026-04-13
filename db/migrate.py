"""
Project migration runner.

Works like a minimal Flyway or Alembic, no extra dependencies:

1. Creates the `schema_migrations` table if missing (tracks applied versions).
2. Reads every .sql file in /migrations/ in lexical (numeric-prefix) order.
3. Runs the ones not yet applied.
4. Records each successful migration in `schema_migrations`.

Why this pattern matters in Data Engineering:
- DB state is versioned the same way as code.
- In a team, nobody applies SQL by hand — everything goes through this script.
- Schema changes ship as new files (002_*.sql); existing ones are never edited.

Bootstrap connection strategy:
- Unlike the rest of the pipeline, `migrate.py` runs *before* schema exists,
  and is the one script that needs to work on any environment (fresh local
  laptop, CI, cloud). It tries three endpoints in order — pooler txn mode,
  pooler session mode, direct connection — so deployment differences don't
  block schema bootstrap. Everything else uses the single shared
  `db.connection.get_connection()`.

Usage:
    python db/migrate.py
"""

import os
import sys
import glob
import psycopg2
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.connection import DB_NAME, POOLER_USER, PROJECT_REF, SSL_MODE

load_dotenv()

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "migrations")

_PASSWORD = os.getenv("SUPABASE_DB_PASSWORD")

# Connection candidates in preference order. Keyword params (not a URL)
# to avoid URL-encoding issues with special characters in passwords
# (e.g. * $ @ #).
_CANDIDATES = [
    # 1. Pooler transaction mode, port 6543 — default on Supabase free tier.
    {
        "host": "aws-1-us-east-1.pooler.supabase.com",
        "port": 6543,
        "user": POOLER_USER,
        "password": _PASSWORD,
        "dbname": DB_NAME,
        "sslmode": SSL_MODE,
        "connect_timeout": 10,
    },
    # 2. Pooler session mode, port 5432.
    {
        "host": "aws-1-us-east-1.pooler.supabase.com",
        "port": 5432,
        "user": POOLER_USER,
        "password": _PASSWORD,
        "dbname": DB_NAME,
        "sslmode": SSL_MODE,
        "connect_timeout": 10,
    },
    # 3. Direct connection (works where the firewall permits it).
    {
        "host": f"db.{PROJECT_REF}.supabase.co",
        "port": 5432,
        "user": "postgres",
        "password": _PASSWORD,
        "dbname": DB_NAME,
        "sslmode": SSL_MODE,
        "connect_timeout": 10,
    },
]


def get_connection():
    """
    Try each candidate in order until one works.
    Makes bootstrap resilient to environment differences (local, CI, cloud).
    """
    errors = []
    for params in _CANDIDATES:
        label = f"{params['host']}:{params['port']}"
        try:
            conn = psycopg2.connect(**params)
            print(f"  Connected via {label}")
            return conn
        except psycopg2.OperationalError as e:
            short_error = str(e).split("\n")[0]
            errors.append(f"  FAIL {label} - {short_error}")

    print("\nCould not reach Supabase. Attempts:")
    for err in errors:
        print(err)
    sys.exit(1)


def ensure_migrations_table(cursor) -> None:
    """
    Create the migration bookkeeping table if it does not exist.
    This table is the source of truth: if a version is here, it has been applied.
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     TEXT        PRIMARY KEY,
            applied_at  TIMESTAMPTZ DEFAULT NOW()
        );
    """)


def get_applied_migrations(cursor) -> set:
    """Return the set of already-applied versions."""
    cursor.execute("SELECT version FROM schema_migrations;")
    return {row[0] for row in cursor.fetchall()}


def get_pending_migrations(applied: set) -> list[tuple[str, str]]:
    """
    Read /migrations/*.sql, filter out applied ones, return a list of
    (version, filepath) sorted by name.

    The numeric prefix (001, 002, ...) enforces the correct sequence.
    """
    pattern = os.path.join(MIGRATIONS_DIR, "*.sql")
    files = sorted(glob.glob(pattern))

    pending = []
    for filepath in files:
        version = os.path.basename(filepath).replace(".sql", "")
        if version not in applied:
            pending.append((version, filepath))

    return pending


def run_migration(cursor, version: str, filepath: str) -> None:
    """
    Execute one .sql file and record its version as applied.
    If the SQL raises, the exception propagates and the caller rolls back.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        sql = f.read()

    print(f"  Applying: {version}")
    cursor.execute(sql)
    cursor.execute(
        "INSERT INTO schema_migrations (version) VALUES (%s);",
        (version,)
    )
    print(f"  OK: {version} applied")


def main() -> None:
    """Entry point: connect, detect pending, apply in order."""
    print("Connecting to Supabase...")
    conn = get_connection()
    conn.autocommit = False
    cursor = conn.cursor()

    try:
        ensure_migrations_table(cursor)
        applied = get_applied_migrations(cursor)
        pending = get_pending_migrations(applied)

        if not pending:
            print("Database up to date. No pending migrations.")
            conn.commit()
            return

        print(f"\n{len(pending)} pending migration(s):")
        for version, filepath in pending:
            run_migration(cursor, version, filepath)

        conn.commit()
        print("\nAll migrations applied successfully.")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR during migration: {e}")
        print("Rolled back. The database was not modified.")
        sys.exit(1)

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
