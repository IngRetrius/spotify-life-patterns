---
quick_id: 260415-x5f
slug: ingest-history
date: 2026-04-15
description: Crear ingestion/ingest_history.py para cargar Extended Streaming History de Spotify en raw_plays
---

## Objetivo

Crear `ingestion/ingest_history.py` que lea los JSON del Extended Streaming History
exportado por Spotify y los inserte en `raw_plays` via upsert idempotente.

## Contexto

- **Fuente**: ~168K records en 15 archivos `Streaming_History_Audio_*.json`
- **Destino**: tabla `raw_plays` (capa bronze del medallion)
- **Reto**: el historial no incluye `artist_id` (Spotify solo expone nombres)
- **Solución**: `uuid5(NAMESPACE_URL, f"artist:{artist_name}")` — determinista, idempotente

## Mapeo de campos

| JSON field                            | raw_plays column | Transformación          |
|---------------------------------------|-----------------|-------------------------|
| `ts`                                  | `played_at`     | Directo (ya UTC ISO)    |
| `spotify_track_uri` → `track:XXXXX`  | `track_id`      | split(":")[2]           |
| `master_metadata_track_name`          | `track_name`    | Directo                 |
| `master_metadata_album_artist_name`   | `artist_name`   | Directo                 |
| `master_metadata_album_album_name`    | `album_name`    | Directo                 |
| `ms_played`                           | `duration_ms`   | Directo (tiempo tocado) |
| (ausente)                             | `artist_id`     | uuid5 sobre artist_name |

## Filtros

- Omitir records donde `spotify_track_uri` es null (episodios/podcasts)
- Omitir records donde `master_metadata_track_name` es null

## Tareas

1. Crear `ingestion/ingest_history.py` siguiendo el estilo de `ingest_plays.py`
2. Commit atómico con el nuevo script
