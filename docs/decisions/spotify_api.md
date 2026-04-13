# Spotify Web API — Hallazgos y decisiones

> Documentación de lo que aprendimos de la API antes de escribir el código de ingesta.
> Fuente: https://developer.spotify.com/documentation/web-api

---

## Endpoints que usamos y sus límites

### 1. Recently Played Tracks
```
GET https://api.spotify.com/v1/me/player/recently-played
```

| Campo | Valor |
|---|---|
| Scope requerido | `user-read-recently-played` |
| Máximo por request | 50 tracks |
| Paginación | Por cursor (before/after en ms Unix), NO por offset |
| No soporta | Episodios de podcast |

**Parámetros útiles:**
- `limit` — cuántos tracks traer (1-50)
- `before` — timestamp en ms: trae tracks reproducidos ANTES de ese momento
- `after` — timestamp en ms: trae tracks reproducidos DESPUÉS de ese momento
- `before` y `after` son mutuamente excluyentes

**Respuesta relevante por item:**
```json
{
  "track": {
    "id": "...",
    "name": "...",
    "duration_ms": 210000,
    "artists": [{ "id": "...", "name": "..." }],
    "album": { "name": "..." }
  },
  "played_at": "2024-01-15T14:30:00Z"
}
```

---

### 2. Audio Features (DEPRECADO)
```
GET https://api.spotify.com/v1/audio-features?ids={ids}
```

| Campo | Valor |
|---|---|
| Scope requerido | Ninguno |
| Máximo IDs por request | 100 |
| **Estado** | **DEPRECADO** — puede ser eliminado por Spotify |

**Campos que retorna:**
| Campo | Tipo | Descripción |
|---|---|---|
| `tempo` | float | BPM estimado |
| `energy` | float 0-1 | Intensidad percibida |
| `danceability` | float 0-1 | Aptitud para bailar |
| `valence` | float 0-1 | Positividad emocional |
| `acousticness` | float 0-1 | Presencia acústica |
| `instrumentalness` | float 0-1 | Ausencia de voz |
| `loudness` | float (dB) | Volumen promedio |
| `speechiness` | float 0-1 | Palabras habladas |
| `liveness` | float 0-1 | Probabilidad de ser en vivo |
| `key` | int -1 a 11 | Clave musical |
| `mode` | int 0/1 | 0=menor, 1=mayor |
| `time_signature` | int 3-7 | Compás |

**Decisión tomada:** implementar con try/except y marcar los features como NULL
si el endpoint falla. El pipeline no debe romperse si Spotify elimina este endpoint.

---

### 3. Get Several Artists (géneros DEPRECADOS)
```
GET https://api.spotify.com/v1/artists?ids={ids}
```

| Campo | Valor |
|---|---|
| Scope requerido | Ninguno |
| Máximo IDs por request | 50 |

**Campos que retorna:**
- `id`, `name` — estables
- `genres` — array de strings. **DEPRECADO**
- `popularity` — entero 0-100. **DEPRECADO**
- `followers` — **DEPRECADO**

**Decisión tomada:** guardar géneros como dato opcional. La lógica de `dominant_genre`
en `session_features` funciona si hay géneros, pero no falla si el array viene vacío.
En fases futuras se puede reemplazar con clasificación propia por nombre de artista o playlist.

---

## Autenticación — Authorization Code Flow

```
Usuario → Tu app → Spotify /authorize → Usuario aprueba → callback con code
→ Tu app intercambia code por (access_token + refresh_token)
→ access_token dura 1 hora → refresh_token renueva sin intervención del usuario
```

**¿Por qué Authorization Code y no Client Credentials?**

Client Credentials autentica la *app*, no el *usuario*. El endpoint `recently-played`
requiere saber quién es el usuario. Solo Authorization Code da acceso a endpoints
de usuario (los que tienen scope `user-read-*`).

**spotipy maneja todo esto automáticamente:**
- Guarda tokens en `.cache` (ya está en `.gitignore`)
- Renueva el `access_token` con el `refresh_token` cuando expira
- La primera vez abre el navegador para que el usuario autorice

---

## Rate Limits

**Cómo funciona:**
- Ventana rodante de **30 segundos**
- En modo desarrollo (apps nuevas): límite más bajo, no publicado
- Al superarlo: `HTTP 429` con header `Retry-After: N` (segundos a esperar)

**Estrategia implementada en el pipeline:**
```python
# Si la API responde 429, esperar exactamente lo que dice Retry-After
# Si no hay header, usar exponential backoff: 1s, 2s, 4s, 8s...
```

**Cómo minimizar llamadas (buenas prácticas de Spotify):**
1. Usar endpoints batch: `/audio-features?ids=id1,id2,...,id100`
   en vez de llamar una vez por track
2. No re-fetchear datos que ya tenemos: si `track_id` ya está en
   `raw_audio_features`, no volver a pedir sus features
3. El pipeline de ingesta corre cada 6 horas, no en tiempo real

---

## Resumen de límites batch para el pipeline

| Lo que pedimos | Endpoint | IDs por call | Estrategia |
|---|---|---|---|
| Historial | `/me/player/recently-played` | 50 tracks | Cursor pagination con `before` |
| Audio features | `/audio-features` | 100 IDs | Agrupar en chunks de 100 |
| Artistas | `/artists` | 50 IDs | Agrupar en chunks de 50 |

---

## Impacto de las deprecaciones en el diseño

Dos deprecaciones afectan nuestro schema:

| Deprecación | Afecta | Decisión |
|---|---|---|
| `/audio-features` endpoint | `raw_audio_features` | Insertar NULL si falla. Pipeline no se rompe. |
| `genres` y `popularity` en `/artists` | `dominant_genre` en `session_features` | Tratar como opcional. Si viene vacío, `dominant_genre = NULL`. |

**Por qué esto importa para el portfolio:**
Documentar que sabías de las deprecaciones y diseñaste alrededor de ellas demuestra
madurez de ingeniería. Un pipeline que se rompe cuando la API cambia es un pipeline
mal diseñado.

---

## Scope configurado en el proyecto

```python
# config/settings.py
SPOTIFY_SCOPE = "user-read-recently-played"
```

Es el único scope necesario. No pedimos más permisos de los que necesitamos
(principio de mínimo privilegio).
