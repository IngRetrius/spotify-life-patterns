"""
Ingesta de metadata de artistas desde Spotify.

Estrategia:
1. Consulta raw_plays para obtener artist_ids unicos
2. Filtra los que ya estan en raw_artists (no re-fetchear)
3. Agrupa en batches de 50 (limite del endpoint /artists)
4. Hace upsert en raw_artists

Nota sobre campos deprecated:
- genres y popularity estan marcados como deprecated en la API
- Siguen funcionando hoy — se guardan si vienen, se guardan como NULL si no
- dominant_genre en session_features depende de este dato

Uso:
    python ingestion/ingest_artists.py
"""

import sys
import time
import psycopg2
import psycopg2.extras
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyException
from dotenv import load_dotenv
import os

load_dotenv()

SPOTIFY_SCOPE       = "user-read-recently-played"
ARTISTS_BATCH       = 50
MAX_RETRY_ATTEMPTS  = 3
RETRY_BACKOFF_BASE  = 2


# ── Conexiones ───────────────────────────────────────────────────────────────

def get_spotify_client() -> spotipy.Spotify:
    return spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
        scope=SPOTIFY_SCOPE,
        cache_path=".cache",
    ))


def get_db_connection():
    return psycopg2.connect(
        host="aws-1-us-east-1.pooler.supabase.com",
        port=6543,
        user="postgres.ofjjslcrzzllzaiiygya",
        password=os.getenv("SUPABASE_DB_PASSWORD"),
        dbname="postgres",
        sslmode="require",
    )


# ── Logica de base de datos ───────────────────────────────────────────────────

def get_artists_without_metadata(cursor) -> list[dict]:
    """
    Retorna artist_id + artist_name de raw_plays para artistas que
    aun no estan en raw_artists.

    Traemos el name desde raw_plays como fallback: si el endpoint
    /artists falla (403), al menos guardamos el nombre que ya tenemos.
    """
    cursor.execute("""
        SELECT DISTINCT ON (rp.artist_id) rp.artist_id, rp.artist_name
        FROM raw_plays rp
        LEFT JOIN raw_artists ra ON rp.artist_id = ra.artist_id
        WHERE ra.artist_id IS NULL
          AND rp.artist_id IS NOT NULL
    """)
    return [{"artist_id": row[0], "artist_name": row[1]} for row in cursor.fetchall()]


UPSERT_ARTISTS_SQL = """
    INSERT INTO raw_artists (artist_id, name, genres, popularity)
    VALUES (%(artist_id)s, %(name)s, %(genres)s, %(popularity)s)
    ON CONFLICT (artist_id) DO NOTHING;
"""


def upsert_artists(cursor, artists: list[dict]) -> int:
    """Inserta artistas. Ignora duplicados por artist_id."""
    if not artists:
        return 0
    psycopg2.extras.execute_batch(cursor, UPSERT_ARTISTS_SQL, artists, page_size=50)
    return cursor.rowcount


# ── Logica de Spotify ─────────────────────────────────────────────────────────

def chunk(lst: list, size: int):
    """Divide una lista en sublistas de tamano 'size'."""
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def fetch_artists(sp: spotipy.Spotify, artist_ids: list[str], fallback_names: dict) -> list[dict]:
    """
    Llama a /artists para un batch de hasta 50 IDs.

    genres y popularity son campos deprecated — se guardan si vienen,
    se guardan como NULL si el campo viene vacio o ausente.
    """
    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            response = sp.artists(artist_ids)
            artists = []

            for artist in response.get("artists", []):
                if artist is None:
                    continue

                genres = artist.get("genres") or []

                artists.append({
                    "artist_id":  artist["id"],
                    "name":       artist["name"],
                    "genres":     genres if genres else None,
                    "popularity": artist.get("popularity"),
                })

            return artists

        except SpotifyException as e:
            if e.http_status == 429:
                wait = int(e.headers.get("Retry-After", RETRY_BACKOFF_BASE ** attempt))
                print(f"  Rate limit (429). Esperando {wait}s...")
                time.sleep(wait)
            elif e.http_status == 403:
                # Endpoint restringido (cambios API Spotify 2024)
                # Usamos el nombre que ya tenemos en raw_plays como fallback
                print(f"  Endpoint /artists no disponible (403). Guardando nombre desde raw_plays.")
                return [{"artist_id": aid,
                         "name": fallback_names.get(aid, aid),
                         "genres": None,
                         "popularity": None}
                        for aid in artist_ids]
            else:
                raise

    raise RuntimeError(f"Se agotaron {MAX_RETRY_ATTEMPTS} intentos contra /artists")


# ── Orquestacion ─────────────────────────────────────────────────────────────

def run() -> None:
    """Ejecuta la ingesta de metadata de artistas."""
    print("=== Ingesta de artistas ===")

    sp   = get_spotify_client()
    conn = get_db_connection()
    conn.autocommit = False
    cursor = conn.cursor()

    total_inserted = 0

    try:
        pending = get_artists_without_metadata(cursor)

        if not pending:
            print("Todos los artistas ya tienen metadata. Nada que hacer.")
            return

        # Mapa artist_id -> artist_name para usar como fallback si /artists falla
        fallback_names = {p["artist_id"]: p["artist_name"] for p in pending}
        artist_ids     = list(fallback_names.keys())

        print(f"{len(artist_ids)} artistas sin metadata. Procesando en batches de {ARTISTS_BATCH}...")

        for i, batch in enumerate(chunk(artist_ids, ARTISTS_BATCH)):
            print(f"\n  Batch {i + 1} ({len(batch)} artistas)...")
            artists  = fetch_artists(sp, batch, fallback_names)
            inserted = upsert_artists(cursor, artists)
            conn.commit()
            total_inserted += inserted
            print(f"  Insertados: {inserted}")

            # Mostrar muestra de generos para verificar que llegan
            sample_genres = [
                f"{a['name']}: {a['genres']}"
                for a in artists[:3]
                if a.get("genres")
            ]
            for s in sample_genres:
                print(f"    {s}")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        sys.exit(1)

    finally:
        cursor.close()
        conn.close()

    print(f"\nResumen: {total_inserted} artistas insertados en raw_artists.")


if __name__ == "__main__":
    run()
