"""
Configuración central del proyecto.

Carga todas las variables de entorno desde .env y las expone
como constantes tipadas. Cualquier módulo que necesite credenciales
importa desde aquí — nunca lee .env directamente.

Por qué centralizar la config:
- Un solo lugar para cambiar si las variables rotan
- Falla rápido (al arrancar) si falta alguna variable crítica
- Facilita unit testing: mockear este módulo es suficiente
"""

import os
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    """Obtiene una variable de entorno obligatoria. Falla si no existe."""
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(
            f"Variable de entorno requerida no encontrada: '{key}'. "
            f"Revisa tu archivo .env"
        )
    return value


# ── Spotify ──────────────────────────────────────────────────────────────────
SPOTIFY_CLIENT_ID: str = _require("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET: str = _require("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI: str = os.getenv(
    "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback"
)
SPOTIFY_SCOPE: str = "user-read-recently-played"

# ── Supabase ─────────────────────────────────────────────────────────────────
SUPABASE_URL: str = _require("SUPABASE_URL")
SUPABASE_ANON_KEY: str = _require("SUPABASE_ANON_KEY")
SUPABASE_DB_URL: str = _require("SUPABASE_DB_URL")

# ── Pipeline ─────────────────────────────────────────────────────────────────
# Gap máximo (en minutos) entre canciones para considerarlas de la misma sesión
SESSION_GAP_MINUTES: int = 30

# Límite de la API de Spotify por request
SPOTIFY_MAX_TRACKS_PER_REQUEST: int = 50
