# Decisión: Audio Features no disponibles — ajuste de estrategia

## Qué pasó

Al ejecutar `ingest_audio_features.py`, el endpoint `/audio-features` retornó
**HTTP 403** — acceso denegado, no solo deprecated.

```
GET /v1/audio-features/?ids=...  →  403 Forbidden
```

## Por qué ocurre

Spotify segmentó sus endpoints en niveles de acceso. A partir de 2024,
`/audio-features` requiere aprobación manual ("Extended Access") que Spotify
otorga solo a aplicaciones comerciales verificadas. Las apps nuevas en
Development Mode reciben 403 directamente.

Esto es independiente de la etiqueta "deprecated" — el endpoint fue deprecado
Y restringido al mismo tiempo.

## Impacto en el diseño

**Features que perdemos:**
- tempo (BPM)
- energy, danceability, valence
- acousticness, instrumentalness
- loudness, speechiness, liveness

**Features que conservamos** (sin necesidad de ese endpoint):

| Feature | Fuente | Cómo se calcula |
|---|---|---|
| `duration_minutes` | raw_plays | sum(duration_ms) / 60000 por sesión |
| `n_tracks` | raw_plays | count de tracks por sesión |
| `n_skips` | raw_plays | tracks donde escuchado < 50% de duration_ms |
| `hour_of_day` | raw_plays.played_at | EXTRACT(hour FROM played_at) |
| `day_of_week` | raw_plays.played_at | EXTRACT(dow FROM played_at) |
| `dominant_genre` | raw_artists.genres | moda de géneros en la sesión |

## Ajuste en las reglas heurísticas

Las actividades se infieren con las features disponibles:

```
DUCHA
  - duration_minutes BETWEEN 5 AND 15
  - n_skips < 2  (no puede interactuar con el telefono)
  - hour_of_day IN (6,7,8,9) OR hour_of_day IN (21,22,23)

GIMNASIO
  - duration_minutes BETWEEN 45 AND 90
  - n_skips < 5  (musica continua)
  - Patron recurrente: mismo day_of_week, misma hour_of_day

TRABAJO / CONCENTRACION
  - duration_minutes > 90
  - hour_of_day BETWEEN 8 AND 18
  - day_of_week BETWEEN 0 AND 4  (lunes a viernes)

DESCANSO / NOCHE
  - hour_of_day BETWEEN 22 AND 24 OR hour_of_day IN (0, 1)
  - n_skips bajo (escucha pasiva)

MOTO
  - Sesion continua (gap entre canciones < 5 min)
  - n_skips = 0  (no puede interactuar)
  - duration_minutes variable
```

## Por qué esto importa para el portfolio

Documentar que el endpoint fue restringido y que el proyecto se adaptó
demuestra capacidad de reacción ante cambios de API — algo muy común
en Data Engineering real. Un pipeline que depende de un solo endpoint
sin manejo de errores es frágil; este proyecto lo resuelve con degradación
elegante (NULL storage + reglas ajustadas).

## Estado en raw_audio_features

Los 50 tracks en raw_plays quedaron registrados en raw_audio_features
con todos los campos en NULL (excepto track_id). Esto evita que el
pipeline reintente fetchear features en cada corrida futura, desperdiciando
llamadas API que van a fallar de todas formas.
