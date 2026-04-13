"""
Cliente de base de datos.

Provee dos formas de conectarse a Supabase según el caso de uso:

1. get_supabase_client() → cliente oficial de supabase-py
   Útil para operaciones simples: insert, select, upsert via REST API.

2. get_db_engine() → SQLAlchemy engine con conexión directa a Postgres
   Útil para el pipeline: queries complejas, pandas.read_sql(), transacciones.

Por qué dos clientes:
- El cliente supabase-py es más expresivo para operaciones CRUD simples
- SQLAlchemy es el estándar en Data Engineering para trabajar con DataFrames
"""

from supabase import create_client, Client
from sqlalchemy import create_engine, Engine
from config.settings import SUPABASE_URL, SUPABASE_ANON_KEY, SUPABASE_DB_URL


def get_supabase_client() -> Client:
    """
    Retorna el cliente oficial de supabase-py.

    Usa la anon key — adecuado para operaciones del pipeline
    ya que las tablas no tienen Row Level Security restrictiva.
    """
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def get_db_engine() -> Engine:
    """
    Retorna un SQLAlchemy engine con conexión directa a Postgres.

    Ideal para:
    - pandas.read_sql() en transformaciones
    - Queries con JOINs complejos
    - Carga masiva con DataFrame.to_sql()
    """
    return create_engine(SUPABASE_DB_URL)
