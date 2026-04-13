# Decisiones de diseño — Base de datos

> Este archivo documenta el razonamiento detrás de cada decisión de diseño del schema.
> Es la respuesta a "¿por qué diseñaste la base de datos así?" en una entrevista.

---

## La decisión más importante: dos capas separadas

El schema tiene 6 tablas divididas en dos grupos con propósitos completamente distintos:

```
RAW LAYER (Bronze)        ANALYTICS LAYER (Silver/Gold)
─────────────────         ─────────────────────────────
raw_plays                 sessions
raw_audio_features        session_features
raw_artists               activity_labels
```

**Raw layer** = datos tal como llegaron de la API de Spotify. Nunca se modifican.

**Analytics layer** = datos calculados por nosotros. Se pueden borrar y recalcular.

### Por qué importa esta separación

Imagina que en 3 meses cambias la lógica de cómo defines una "sesión" (por ejemplo,
de 30 minutos de gap a 20 minutos). Con esta separación:

- Borras `sessions`, `session_features`, `activity_labels`
- Corres de nuevo la transformación
- Los datos crudos siguen intactos en `raw_plays`

Sin esta separación, perderías los datos originales de Spotify para siempre.

Este patrón tiene nombre: **Medallion Architecture** (Bronze → Silver → Gold).
Es el estándar en la industria — lo usan Databricks, Snowflake, dbt.

---

## Por qué `sessions`, `session_features` y `activity_labels` son 3 tablas y no 1

Podrías haber puesto todo en una tabla `sessions` con 20 columnas. No se hizo así
porque cada tabla tiene una **razón de cambio diferente**:

| Tabla | Responde a | Cambia cuando |
|---|---|---|
| `sessions` | ¿Cuándo ocurrió esta sesión? | Cambia la definición de gap (30 min) |
| `session_features` | ¿Cómo sonó musicalmente? | Cambian los audio features que usamos |
| `activity_labels` | ¿Qué actividad era? | Cambian las reglas o el modelo de ML |

Esto se llama **Single Responsibility Principle** aplicado a tablas.

Beneficio concreto: cuando en fase 2 reemplaces las reglas heurísticas por un modelo
de ML, solo tocas `activity_labels`. Las sesiones y sus features no cambian.

---

## `UNIQUE (track_id, played_at)` — idempotencia del pipeline

```sql
UNIQUE (track_id, played_at)
```

El cron corre cada 6 horas. Spotify retorna los últimos 50 tracks. Una canción
reproducida a las 5pm puede aparecer en el run de las 4pm Y en el de las 6pm.

Sin este constraint: la misma reproducción se insertaría dos veces, tus sesiones
quedarían duplicadas, y tus métricas del dashboard serían incorrectas.

Con este constraint: el insert hace **upsert** — inserta si no existe, ignora si ya
está. Puedes correr el pipeline 100 veces sobre los mismos datos y el resultado
siempre es el mismo.

**Propiedad que esto garantiza: idempotencia.**

> En Data Engineering, un pipeline idempotente es uno donde ejecutarlo N veces
> produce exactamente el mismo resultado que ejecutarlo 1 vez. Es una propiedad
> fundamental para tener pipelines confiables.

---

## `TIMESTAMPTZ` y no `TIMESTAMP`

```sql
played_at TIMESTAMPTZ NOT NULL
```

| Tipo | Comportamiento |
|---|---|
| `TIMESTAMP` | Guarda la hora sin zona horaria. Lo que insertes es lo que queda. |
| `TIMESTAMPTZ` | Guarda en UTC internamente. Convierte al timezone del cliente al leer. |

Spotify reporta `played_at` en UTC. Colombia está en UTC-5. Si usaras `TIMESTAMP`
y mezclaras timestamps de distintas fuentes, tus análisis por hora del día quedarían
desfasados 5 horas.

**Regla general:** siempre UTC en la base de datos. Convierte al timezone del usuario
solo en la capa de presentación (el dashboard en Streamlit).

---

## `TEXT[]` para géneros — arrays nativos de Postgres

```sql
genres TEXT[]   -- ejemplo: ["reggaeton", "latin pop", "urbano latino"]
```

Un artista tiene múltiples géneros en Spotify. Las alternativas evaluadas:

| Opción | Por qué se descartó |
|---|---|
| `TEXT` con JSON string `'["reggaeton","pop"]'` | Difícil de filtrar. `LIKE '%reggaeton%'` es frágil y lento |
| Tabla separada `artist_genres` | Overkill — agrega un JOIN en cada query por una relación simple |
| `TEXT[]` array nativo | Filtrable, indexable, sin overhead |

Con array nativo puedes hacer queries limpias:
```sql
-- Todas las sesiones donde el artista es reggaeton
SELECT * FROM raw_artists WHERE 'reggaeton' = ANY(genres);
```

---

## `ON DELETE CASCADE` — integridad referencial

```sql
session_id UUID REFERENCES sessions(session_id) ON DELETE CASCADE
```

`session_features` y `activity_labels` no tienen significado sin su sesión padre.
Si borras una sesión (para recalcular), el `CASCADE` borra automáticamente sus
features y labels asociados.

Sin `CASCADE`: quedarían **filas huérfanas** — datos que referencian una sesión que
ya no existe. Eso corrompe silenciosamente tus análisis porque los JOINs devuelven
resultados incorrectos sin lanzar ningún error.

---

## UUIDs vs enteros autoincrement

```sql
id UUID DEFAULT gen_random_uuid() PRIMARY KEY
```

| Primary key | Cómo funciona |
|---|---|
| `SERIAL` / `BIGSERIAL` | La base de datos genera el ID al hacer INSERT. No sabes el ID antes de insertar. |
| `UUID` | Puedes generar el ID en Python antes de insertar. |

En el pipeline de transformación, cuando construyes una sesión en Python, necesitas
el `session_id` para insertar en `sessions` Y en `session_features` al mismo tiempo.

Con UUID: generas `session_id = uuid.uuid4()` en Python y lo usas en ambos inserts
directamente.

Con SERIAL: harías INSERT en `sessions`, luego SELECT para obtener el ID generado,
luego INSERT en `session_features`. Dos roundtrips a la base de datos en lugar de uno.

---

## Los índices — por qué esos y no otros

```sql
CREATE INDEX idx_raw_plays_played_at   ON raw_plays (played_at DESC);
CREATE INDEX idx_raw_plays_track_id    ON raw_plays (track_id);
CREATE INDEX idx_sessions_start_time   ON sessions  (start_time DESC);
CREATE INDEX idx_activity_labels_label ON activity_labels (activity_label);
```

Cada índice existe porque hay una query frecuente que lo justifica:

| Índice | Query que acelera |
|---|---|
| `played_at DESC` | Construcción de sesiones: ordenar todos los plays por tiempo |
| `track_id` | JOIN con `raw_audio_features` para enriquecer cada play |
| `start_time DESC` | Dashboard: "sesiones de esta semana / último mes" |
| `activity_label` | Dashboard: "todas las sesiones de gym" |

**Por qué no se indexó todo:** cada índice tiene un costo en velocidad de escritura
(el índice se actualiza en cada INSERT). Solo se crean índices donde el patrón de
lectura lo justifica.

---

## Resumen ejecutivo para entrevistas

Tres principios aplicados en este diseño:

1. **Inmutabilidad del dato crudo** (Medallion Architecture)
   Los datos de la API nunca se modifican. Todo procesamiento produce tablas nuevas.
   Permite reprocesar sin perder información original.

2. **Single Responsibility por tabla**
   Cada tabla tiene una sola razón de cambiar. Facilita evolucionar el pipeline
   por partes sin afectar el resto.

3. **Idempotencia por constraints**
   El `UNIQUE (track_id, played_at)` hace el pipeline re-ejecutable de forma segura.
   Los pipelines confiables son idempotentes por diseño, no por suerte.

> Respuesta corta para entrevista:
> "Separé raw de analytics para tener datos inmutables y poder reprocesar sin perder
> información. Dentro de analytics apliqué Single Responsibility para que cada capa
> de la transformación pueda cambiar de forma independiente. Los constraints de
> unicidad hacen el pipeline idempotente — puedo correrlo N veces sin efectos
> secundarios."
