"""
Carga del Extended Streaming History exportado por Spotify en raw_plays.

Spotify permite exportar el historial completo (años de datos) en formato JSON
a traves de la pagina de privacidad. Este script lo ingesta en la capa bronze
(raw_plays) del medallion, respetando el mismo contrato de upsert idempotente
que ingest_plays.py.

Diferencias respecto a ingest_plays.py:
- Lee archivos JSON locales en vez de llamar a la API
- El historial exportado NO incluye artist_id — se genera deterministicamente
  con uuid5(NAMESPACE_URL, "artist:{artist_name}") para que cada re-ejecucion
  produzca el mismo ID y el upsert sea seguro
- duration_ms = ms_played (tiempo reproducido, no duracion total del track)
- Filtra episodios/podcasts: solo procesa records con spotify_track_uri

Uso:
    python ingestion/ingest_history.py --source-dir "ruta/al/historial"
    python ingestion/ingest_history.py  # usa SOURCE_DIR del .env o la ruta por defecto
"""

import sys
import os
import glob
import json
import uuid
import argparse
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.connection import get_connection as get_db_connection

load_dotenv()

# ── Constantes ────────────────────────────────────────────────────────────────

NAMESPACE      = uuid.NAMESPACE_URL   # base para uuid5 deterministico
BATCH_SIZE     = 500                  # filas por execute_batch

DEFAULT_SOURCE = os.getenv(
    "HISTORY_SOURCE_DIR",
    r"C:\Users\USUARIO1\Downloads\my_spotify_data\Spotify Extended Streaming History",
)


# ── Lectura de archivos ───────────────────────────────────────────────────────

def find_audio_files(source_dir: str) -> list[str]:
    """
    Retorna todos los archivos Streaming_History_Audio_*.json del directorio,
    ordenados por nombre (el prefijo de año garantiza el orden cronologico).
    """
    pattern = os.path.join(source_dir, "Streaming_History_Audio_*.json")
    files = sorted(glob.glob(pattern))
    if not files:
        raise FileNotFoundError(
            f"No se encontraron archivos Streaming_History_Audio_*.json en: {source_dir}"
        )
    return files


def make_artist_id(artist_name: str) -> str:
    """
    Genera un UUID deterministico a partir del nombre del artista.

    Por que uuid5 y no el ID real de Spotify:
    - El historial exportado no incluye artist_id, solo el nombre
    - uuid5 garantiza que el mismo nombre siempre produce el mismo UUID
    - Esto hace el upsert idempotente: re-ejecutar con los mismos datos
      no genera duplicados ni cambia IDs existentes
    """
    return str(uuid.uuid5(NAMESPACE, f"artist:{artist_name}"))


def parse_record(record: dict) -> dict | None:
    """
    Convierte un record del JSON exportado al formato de raw_plays.

    Retorna None si el record no es un track de musica (episodio, audiobook,
    o campos obligatorios ausentes).
    """
    track_uri  = record.get("spotify_track_uri")
    track_name = record.get("master_metadata_track_name")
    artist_name = record.get("master_metadata_album_artist_name")

    # Filtrar episodios, podcasts y audiobooks
    if not track_uri or not track_name or not artist_name:
        return None

    # Extraer track_id del URI: "spotify:track:XXXX" -> "XXXX"
    parts = track_uri.split(":")
    if len(parts) != 3 or parts[1] != "track":
        return None

    track_id = parts[2]

    country = record.get("conn_country")

    return {
        "track_id":    track_id,
        "track_name":  track_name,
        "artist_id":   make_artist_id(artist_name),
        "artist_name": artist_name,
        "album_name":  record.get("master_metadata_album_album_name"),
        "duration_ms": record.get("ms_played"),
        "played_at":   record.get("ts"),
        "conn_country": country if country and country != "ZZ" else None,
    }


def load_file(filepath: str) -> list[dict]:
    """
    Lee un archivo JSON y retorna los records validos (solo tracks de musica).
    Los records invalidos se omiten silenciosamente.
    """
    with open(filepath, encoding="utf-8") as f:
        raw = json.load(f)

    plays = []
    for record in raw:
        parsed = parse_record(record)
        if parsed:
            plays.append(parsed)
    return plays


# ── Logica de base de datos ───────────────────────────────────────────────────

UPSERT_SQL = """
    INSERT INTO raw_plays
        (track_id, track_name, artist_id, artist_name, album_name, duration_ms, played_at,
         conn_country)
    VALUES
        (%(track_id)s, %(track_name)s, %(artist_id)s, %(artist_name)s,
         %(album_name)s, %(duration_ms)s, %(played_at)s,
         %(conn_country)s)
    ON CONFLICT (track_id, played_at) DO UPDATE SET
        conn_country = EXCLUDED.conn_country
    WHERE raw_plays.conn_country IS NULL;
"""


def upsert_plays(cursor, plays: list[dict]) -> int:
    """
    Inserta un lote de plays en raw_plays.
    Los duplicados (mismo track_id + played_at) se ignoran silenciosamente.

    Por que acumulamos rowcount manualmente:
    - execute_batch divide los datos en sub-batches de page_size filas
    - cursor.rowcount solo refleja el ultimo sub-batch, no el total
    - Iteramos manualmente para obtener el conteo real de inserciones
    """
    if not plays:
        return 0

    total_inserted = 0
    for i in range(0, len(plays), BATCH_SIZE):
        batch = plays[i : i + BATCH_SIZE]
        psycopg2.extras.execute_batch(cursor, UPSERT_SQL, batch, page_size=BATCH_SIZE)
        total_inserted += cursor.rowcount

    return total_inserted


# ── Orquestacion ─────────────────────────────────────────────────────────────

def run(source_dir: str = DEFAULT_SOURCE) -> dict:
    """
    Carga todos los archivos del historial exportado en raw_plays.

    Args:
        source_dir: directorio con los archivos Streaming_History_Audio_*.json

    Returns:
        Dict con estadisticas: total_read, total_inserted, total_skipped, files_processed
    """
    print("=== Carga de Extended Streaming History ===")
    print(f"Fuente: {source_dir}")

    files = find_audio_files(source_dir)
    print(f"Archivos encontrados: {len(files)}")

    conn = get_db_connection()
    conn.autocommit = False
    cursor = conn.cursor()

    total_read     = 0
    total_inserted = 0
    total_skipped  = 0  # episodios/podcasts filtrados

    try:
        for filepath in files:
            filename = os.path.basename(filepath)
            plays    = load_file(filepath)

            # Registrar cuantos records originales habia en el archivo
            with open(filepath, encoding="utf-8") as f:
                raw_count = len(json.load(f))
            file_skipped = raw_count - len(plays)

            if not plays:
                print(f"  {filename}: 0 tracks de musica (todos omitidos)")
                total_skipped += file_skipped
                continue

            inserted = upsert_plays(cursor, plays)
            conn.commit()

            duplicates = len(plays) - inserted
            total_read     += len(plays)
            total_inserted += inserted
            total_skipped  += file_skipped

            print(
                f"  {filename}: {len(plays)} tracks"
                f" | Nuevos: {inserted}"
                f" | Ya existian: {duplicates}"
                + (f" | No-musica omitidos: {file_skipped}" if file_skipped else "")
            )

    except Exception as e:
        conn.rollback()
        print(f"\nERROR: {e}")
        sys.exit(1)

    finally:
        cursor.close()
        conn.close()

    print(f"\nResumen:")
    print(f"  Tracks de musica procesados : {total_read}")
    print(f"  Insertados en raw_plays     : {total_inserted}")
    print(f"  Ya existian (duplicados)    : {total_read - total_inserted}")
    print(f"  Episodios/no-musica omitidos: {total_skipped}")

    return {
        "total_read":      total_read,
        "total_inserted":  total_inserted,
        "total_skipped":   total_skipped,
        "files_processed": len(files),
    }


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Carga el Extended Streaming History exportado por Spotify en raw_plays"
    )
    parser.add_argument(
        "--source-dir",
        default=DEFAULT_SOURCE,
        help=(
            "Directorio con los archivos Streaming_History_Audio_*.json "
            f"(default: {DEFAULT_SOURCE})"
        ),
    )
    args = parser.parse_args()
    run(source_dir=args.source_dir)
