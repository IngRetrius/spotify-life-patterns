"""
Ingesta de historial de reproducciones desde Spotify.

Trae los ultimos tracks reproducidos y los guarda en raw_plays (Supabase).

Decisiones de diseno:
- Upsert por (track_id, played_at): idempotente, seguro de re-ejecutar
- Paginacion por cursor 'before': permite traer mas de 50 tracks en una sola corrida
- Retry con Retry-After: respeta los rate limits de Spotify sin romper el pipeline
- Registra cuantos tracks se insertaron vs cuantos ya existian

Uso:
    python ingestion/ingest_plays.py              # trae los ultimos 50
    python ingestion/ingest_plays.py --pages 5    # trae hasta 250 (5 x 50)
"""

import sys
import time
import argparse
import psycopg2
import psycopg2.extras
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyException
from dotenv import load_dotenv
import os

# Allow `python ingestion/ingest_plays.py` from project root.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.connection import get_connection as get_db_connection

load_dotenv()

# ── Constantes ───────────────────────────────────────────────────────────────

SPOTIFY_SCOPE        = "user-read-recently-played"
SPOTIFY_MAX_LIMIT    = 50   # maximo que permite el endpoint
MAX_RETRY_ATTEMPTS   = 3
RETRY_BACKOFF_BASE   = 2    # segundos base para exponential backoff


# ── Conexiones ───────────────────────────────────────────────────────────────

def get_spotify_client() -> spotipy.Spotify:
    """Retorna cliente de Spotify autenticado. Usa token cacheado si existe."""
    return spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
        scope=SPOTIFY_SCOPE,
        cache_path=".cache",
    ))


# ── Logica de Spotify ─────────────────────────────────────────────────────────

def fetch_recent_plays(sp: spotipy.Spotify, before_ms: int = None) -> dict:
    """
    Llama a /me/player/recently-played con retry en rate limit.

    Args:
        before_ms: cursor Unix timestamp en ms. Si es None trae los mas recientes.

    Returns:
        Respuesta cruda de la API (CursorPagingObject).
    """
    params = {"limit": SPOTIFY_MAX_LIMIT}
    if before_ms:
        params["before"] = before_ms

    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            return sp.current_user_recently_played(**params)
        except SpotifyException as e:
            if e.http_status == 429:
                wait = int(e.headers.get("Retry-After", RETRY_BACKOFF_BASE ** attempt))
                print(f"  Rate limit (429). Esperando {wait}s...")
                time.sleep(wait)
            else:
                raise

    raise RuntimeError(f"Se agotaron {MAX_RETRY_ATTEMPTS} intentos contra la API de Spotify")


def parse_plays(response: dict) -> list[dict]:
    """
    Extrae los campos que necesitamos de la respuesta de la API.

    La API retorna objetos anidados (track > artists > ...).
    Aplanamos lo que va a raw_plays.
    """
    plays = []
    for item in response.get("items", []):
        track = item["track"]
        artists = track.get("artists", [])

        plays.append({
            "track_id":   track["id"],
            "track_name": track["name"],
            "artist_id":  artists[0]["id"] if artists else None,
            "artist_name": artists[0]["name"] if artists else None,
            "album_name": track.get("album", {}).get("name"),
            "duration_ms": track.get("duration_ms"),
            "played_at":  item["played_at"],
        })
    return plays


# ── Logica de base de datos ───────────────────────────────────────────────────

UPSERT_SQL = """
    INSERT INTO raw_plays
        (track_id, track_name, artist_id, artist_name, album_name, duration_ms, played_at)
    VALUES
        (%(track_id)s, %(track_name)s, %(artist_id)s, %(artist_name)s,
         %(album_name)s, %(duration_ms)s, %(played_at)s)
    ON CONFLICT (track_id, played_at) DO NOTHING;
"""


def upsert_plays(cursor, plays: list[dict]) -> int:
    """
    Inserta los plays en raw_plays. Los duplicados se ignoran silenciosamente.

    Retorna cuantas filas se insertaron realmente (las nuevas).

    Por que executemany y no execute en loop:
    - executemany envia todos los registros en una sola transaccion
    - Menos roundtrips a la base de datos = mas rapido
    """
    if not plays:
        return 0

    before = cursor.rowcount if cursor.rowcount >= 0 else 0
    psycopg2.extras.execute_batch(cursor, UPSERT_SQL, plays, page_size=50)

    # rowcount con ON CONFLICT DO NOTHING cuenta solo las filas efectivamente insertadas
    return cursor.rowcount


# ── Orquestacion ─────────────────────────────────────────────────────────────

def run(max_pages: int = 1) -> None:
    """
    Ejecuta el pipeline de ingesta.

    Args:
        max_pages: cuantas paginas de 50 tracks traer (default: 1 = 50 tracks).
    """
    print("=== Ingesta de plays ===")

    sp = get_spotify_client()
    conn = get_db_connection()
    conn.autocommit = False
    cursor = conn.cursor()

    total_fetched  = 0
    total_inserted = 0
    before_ms      = None   # cursor para paginacion

    try:
        for page in range(max_pages):
            print(f"\nPagina {page + 1}/{max_pages}...")

            response = fetch_recent_plays(sp, before_ms=before_ms)
            plays    = parse_plays(response)

            if not plays:
                print("  No hay mas tracks. Pipeline terminado.")
                break

            inserted = upsert_plays(cursor, plays)
            conn.commit()

            total_fetched  += len(plays)
            total_inserted += inserted
            duplicates      = len(plays) - inserted

            print(f"  Traidos: {len(plays)} | Insertados: {inserted} | Ya existian: {duplicates}")

            # El cursor 'before' de la siguiente pagina es el timestamp
            # del track MAS ANTIGUO de esta pagina (en ms)
            cursors  = response.get("cursors") or {}
            before_str = cursors.get("before")
            if not before_str:
                print("  No hay pagina anterior. Fin del historial disponible.")
                break
            before_ms = int(before_str)

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        sys.exit(1)

    finally:
        cursor.close()
        conn.close()

    print(f"\nResumen: {total_fetched} traidos, {total_inserted} nuevos insertados en raw_plays.")


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingesta de historial de Spotify")
    parser.add_argument(
        "--pages", type=int, default=1,
        help="Cuantas paginas de 50 tracks traer (default: 1)"
    )
    args = parser.parse_args()
    run(max_pages=args.pages)
