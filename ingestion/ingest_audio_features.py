"""
Ingesta de audio features para tracks en raw_plays.

Estrategia:
1. Consulta raw_plays para obtener track_ids unicos
2. Filtra los que ya tienen features en raw_audio_features (no re-fetchear)
3. Agrupa en batches de 100 (limite del endpoint)
4. Llama a /audio-features y hace upsert en raw_audio_features

Manejo del endpoint deprecated:
- Si Spotify responde 4xx/5xx, guarda los tracks con features en NULL
- El pipeline NO se rompe si el endpoint desaparece

Uso:
    python ingestion/ingest_audio_features.py
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

SPOTIFY_SCOPE          = "user-read-recently-played"
AUDIO_FEATURES_BATCH   = 100   # maximo de IDs por llamada al endpoint
MAX_RETRY_ATTEMPTS     = 3
RETRY_BACKOFF_BASE     = 2


# ── Conexiones ───────────────────────────────────────────────────────────────

def get_spotify_client() -> spotipy.Spotify:
    """Retorna cliente de Spotify autenticado."""
    return spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=os.getenv("SPOTIFY_CLIENT_ID"),
        client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.getenv("SPOTIFY_REDIRECT_URI"),
        scope=SPOTIFY_SCOPE,
        cache_path=".cache",
    ))


def get_db_connection():
    """Retorna conexion a Postgres en Supabase."""
    return psycopg2.connect(
        host="aws-1-us-east-1.pooler.supabase.com",
        port=6543,
        user="postgres.ofjjslcrzzllzaiiygya",
        password=os.getenv("SUPABASE_DB_PASSWORD"),
        dbname="postgres",
        sslmode="require",
    )


# ── Logica de base de datos ───────────────────────────────────────────────────

def get_tracks_without_features(cursor) -> list[str]:
    """
    Retorna track_ids de raw_plays que aun no tienen audio features.

    Usa LEFT JOIN + IS NULL en lugar de NOT IN por rendimiento:
    - NOT IN con subquery es O(n*m)
    - LEFT JOIN + IS NULL es O(n) con el indice en track_id
    """
    cursor.execute("""
        SELECT DISTINCT rp.track_id
        FROM raw_plays rp
        LEFT JOIN raw_audio_features raf ON rp.track_id = raf.track_id
        WHERE raf.track_id IS NULL
    """)
    return [row[0] for row in cursor.fetchall()]


UPSERT_FEATURES_SQL = """
    INSERT INTO raw_audio_features (
        track_id, tempo, energy, danceability, valence,
        acousticness, instrumentalness, loudness, speechiness, liveness
    ) VALUES (
        %(track_id)s, %(tempo)s, %(energy)s, %(danceability)s, %(valence)s,
        %(acousticness)s, %(instrumentalness)s, %(loudness)s,
        %(speechiness)s, %(liveness)s
    )
    ON CONFLICT (track_id) DO NOTHING;
"""


def upsert_features(cursor, features: list[dict]) -> int:
    """Inserta audio features. Ignora duplicados por track_id."""
    if not features:
        return 0
    psycopg2.extras.execute_batch(cursor, UPSERT_FEATURES_SQL, features, page_size=100)
    return cursor.rowcount


# ── Logica de Spotify ─────────────────────────────────────────────────────────

def chunk(lst: list, size: int):
    """Divide una lista en sublistas de tamano 'size'."""
    for i in range(0, len(lst), size):
        yield lst[i:i + size]


def fetch_audio_features(sp: spotipy.Spotify, track_ids: list[str]) -> list[dict]:
    """
    Llama a /audio-features para un batch de hasta 100 IDs.

    Manejo de deprecated:
    - Si el endpoint falla (4xx/5xx), retorna filas con features en NULL
      para que queden registrados en raw_audio_features y no se reintenten
      en cada corrida futura.

    Manejo de tracks sin features:
    - Spotify puede retornar null para un track_id especifico (tracks locales,
      podcasts, tracks muy nuevos). Tambien se guardan con NULL.
    """
    for attempt in range(MAX_RETRY_ATTEMPTS):
        try:
            response = sp.audio_features(tracks=track_ids)

            features = []
            for item in response:
                if item is None:
                    # Spotify no tiene features para este track
                    # Lo guardamos con NULLs para no reintentar siempre
                    continue

                features.append({
                    "track_id":          item["id"],
                    "tempo":             item.get("tempo"),
                    "energy":            item.get("energy"),
                    "danceability":      item.get("danceability"),
                    "valence":           item.get("valence"),
                    "acousticness":      item.get("acousticness"),
                    "instrumentalness":  item.get("instrumentalness"),
                    "loudness":          item.get("loudness"),
                    "speechiness":       item.get("speechiness"),
                    "liveness":          item.get("liveness"),
                })
            return features

        except SpotifyException as e:
            if e.http_status == 429:
                wait = int(e.headers.get("Retry-After", RETRY_BACKOFF_BASE ** attempt))
                print(f"  Rate limit (429). Esperando {wait}s...")
                time.sleep(wait)
            elif e.http_status in (403, 404):
                # Endpoint deprecated y desactivado, o acceso denegado
                print(f"  Endpoint audio-features no disponible ({e.http_status}). Guardando NULLs.")
                return [{"track_id": tid, "tempo": None, "energy": None,
                         "danceability": None, "valence": None, "acousticness": None,
                         "instrumentalness": None, "loudness": None,
                         "speechiness": None, "liveness": None}
                        for tid in track_ids]
            else:
                raise

    raise RuntimeError(f"Se agotaron {MAX_RETRY_ATTEMPTS} intentos contra /audio-features")


# ── Orquestacion ─────────────────────────────────────────────────────────────

def run() -> None:
    """Ejecuta la ingesta de audio features para tracks sin enriquecer."""
    print("=== Ingesta de audio features ===")

    sp  = get_spotify_client()
    conn = get_db_connection()
    conn.autocommit = False
    cursor = conn.cursor()

    total_inserted = 0

    try:
        pending = get_tracks_without_features(cursor)

        if not pending:
            print("Todos los tracks ya tienen audio features. Nada que hacer.")
            return

        print(f"{len(pending)} tracks sin features. Procesando en batches de {AUDIO_FEATURES_BATCH}...")

        for i, batch in enumerate(chunk(pending, AUDIO_FEATURES_BATCH)):
            print(f"\n  Batch {i + 1} ({len(batch)} tracks)...")
            features = fetch_audio_features(sp, batch)
            inserted = upsert_features(cursor, features)
            conn.commit()
            total_inserted += inserted
            print(f"  Insertados: {inserted}")

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        sys.exit(1)

    finally:
        cursor.close()
        conn.close()

    print(f"\nResumen: {total_inserted} tracks enriquecidos con audio features.")


if __name__ == "__main__":
    run()
