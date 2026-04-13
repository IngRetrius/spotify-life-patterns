"""
Motor de migraciones del proyecto.

Funciona igual que Flyway o Alembic, pero simple y sin dependencias extra:

1. Crea la tabla `schema_migrations` si no existe (guarda qué migraciones corrieron)
2. Lee todos los archivos .sql de /migrations/ en orden numérico
3. Ejecuta solo los que aún no se aplicaron
4. Registra cada migración exitosa en `schema_migrations`

Por qué este patrón importa en Data Engineering:
- El estado de la base de datos queda versionado igual que el código
- En un equipo, nadie aplica SQL manualmente: todo pasa por este script
- Si el schema cambia, se agrega un nuevo archivo 002_*.sql — nunca se edita uno existente

Uso:
    python db/migrate.py
"""

import os
import sys
import glob
import psycopg2
from dotenv import load_dotenv

load_dotenv()

MIGRATIONS_DIR = os.path.join(os.path.dirname(__file__), "..", "migrations")

# Candidatos de conexión en orden de preferencia.
# Usamos parámetros keyword (no URL) para evitar problemas de
# URL-encoding con caracteres especiales en la contraseña (ej: * $ @ #).
_PROJECT_REF = "ofjjslcrzzllzaiiygya"
_PASSWORD = os.getenv("SUPABASE_DB_PASSWORD")

_CANDIDATES = [
    # 1. Pooler transaction mode — puerto 6543 (el más disponible en Supabase free tier)
    {
        "host": "aws-1-us-east-1.pooler.supabase.com",
        "port": 6543,
        "user": f"postgres.{_PROJECT_REF}",
        "password": _PASSWORD,
        "dbname": "postgres",
        "sslmode": "require",
        "connect_timeout": 10,
    },
    # 2. Pooler session mode — puerto 5432
    {
        "host": "aws-1-us-east-1.pooler.supabase.com",
        "port": 5432,
        "user": f"postgres.{_PROJECT_REF}",
        "password": _PASSWORD,
        "dbname": "postgres",
        "sslmode": "require",
        "connect_timeout": 10,
    },
    # 3. Conexión directa (funciona cuando el firewall lo permite)
    {
        "host": f"db.{_PROJECT_REF}.supabase.co",
        "port": 5432,
        "user": "postgres",
        "password": _PASSWORD,
        "dbname": "postgres",
        "sslmode": "require",
        "connect_timeout": 10,
    },
]


def get_connection():
    """
    Prueba los candidatos en orden hasta encontrar uno que funcione.
    Esto nos hace resilientes a diferencias de entorno (local, CI, nube).
    """
    errors = []
    for params in _CANDIDATES:
        label = f"{params['host']}:{params['port']}"
        try:
            conn = psycopg2.connect(**params)
            print(f"  Conectado via {label}")
            return conn
        except psycopg2.OperationalError as e:
            short_error = str(e).split("\n")[0]
            errors.append(f"  FAIL {label} - {short_error}")

    print("\nNo se pudo establecer conexion con Supabase. Intentos:")
    for err in errors:
        print(err)
    sys.exit(1)


def ensure_migrations_table(cursor) -> None:
    """
    Crea la tabla de control de migraciones si no existe.
    Esta tabla es el registro de verdad: si una versión está aquí, ya se aplicó.
    """
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version     TEXT        PRIMARY KEY,
            applied_at  TIMESTAMPTZ DEFAULT NOW()
        );
    """)


def get_applied_migrations(cursor) -> set:
    """Retorna el conjunto de versiones ya aplicadas."""
    cursor.execute("SELECT version FROM schema_migrations;")
    return {row[0] for row in cursor.fetchall()}


def get_pending_migrations(applied: set) -> list[tuple[str, str]]:
    """
    Lee /migrations/*.sql, filtra los ya aplicados y retorna
    una lista de (version, filepath) ordenada por nombre.

    El orden numérico del prefijo (001, 002...) garantiza la secuencia correcta.
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
    Ejecuta un archivo .sql y registra la versión como aplicada.
    Si el SQL falla, la excepción sube y el llamador hace rollback.
    """
    with open(filepath, "r", encoding="utf-8") as f:
        sql = f.read()

    print(f"  Aplicando: {version}")
    cursor.execute(sql)
    cursor.execute(
        "INSERT INTO schema_migrations (version) VALUES (%s);",
        (version,)
    )
    print(f"  OK: {version} aplicada")


def main() -> None:
    """Punto de entrada: conecta, detecta pendientes y aplica en orden."""
    print("Conectando a Supabase...")
    conn = get_connection()
    conn.autocommit = False
    cursor = conn.cursor()

    try:
        ensure_migrations_table(cursor)
        applied = get_applied_migrations(cursor)
        pending = get_pending_migrations(applied)

        if not pending:
            print("Base de datos al día. No hay migraciones pendientes.")
            conn.commit()
            return

        print(f"\n{len(pending)} migración(es) pendiente(s):")
        for version, filepath in pending:
            run_migration(cursor, version, filepath)

        conn.commit()
        print("\nTodas las migraciones aplicadas exitosamente.")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR durante la migración: {e}")
        print("Se hizo rollback. La base de datos no fue modificada.")
        sys.exit(1)

    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
