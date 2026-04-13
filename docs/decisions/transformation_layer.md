# Capa de Transformacion — Decisiones de diseno

## Los tres pasos y por que ese orden

```
build_sessions.py → compute_features.py → label_activities.py
```

Cada paso depende del anterior y tiene una sola responsabilidad.
No se pueden reordenar porque cada uno lee lo que el anterior escribio.

---

## 1. build_sessions.py — construccion de sesiones

### Algoritmo de agrupacion

```
plays ordenados por played_at:
  A (3:00) → B (3:04) → C (3:09) → [gap 45 min] → D (3:54) → ...

gap entre C y D = 45 min > 30 min = nueva sesion

Sesion 1: A, B, C
Sesion 2: D, ...
```

### Por que session_id es deterministico (uuid5)

`session_id = uuid5(NAMESPACE_URL, start_time.isoformat())`

Con UUID aleatorio: cada vez que reconstruyes sesiones, los IDs cambian.
Las referencias desde `session_features` y `activity_labels` quedan huerfanas.

Con UUID deterministico: el mismo start_time siempre produce el mismo ID.
Puedes reconstruir sesiones N veces y el upsert es seguro.

### Calculo de end_time

`end_time = played_at del ultimo track + su duration_ms`

No es simplemente el `played_at` del ultimo track, porque ese timestamp marca
*cuando empezo* esa cancion. Si la sesion termina con una cancion de 3 minutos,
el fin real de la sesion es 3 minutos despues.

### Por que pandas y no SQL puro

La logica de agrupacion por gap requiere comparar cada fila con la anterior.
En SQL esto requiere window functions y self-joins que son verbosos.
En pandas: `df["gap"] = df["played_at"] - df["played_at"].shift(1)` — una linea.

Para datasets pequeños (< millones de filas), pandas en memoria es suficiente.
En una arquitectura con Spark o dbt, esta logica se traduciria a SQL con LAG().

---

## 2. compute_features.py — features por sesion

### Deteccion de skips

```
Un track es "skip" si:
  played_at[i+1] - played_at[i] < duration_ms[i] * 0.5
```

Es decir: si la siguiente cancion empezo antes de que terminara la mitad de la actual.

No podemos saber directamente si el usuario apreto "siguiente" — solo vemos timestamps.
Este proxy es una aproximacion: no captura pausas largas ni escuchas lentas.

### merge_asof para asignar plays a sesiones

En lugar de un JOIN con condicion de rango (lento para datasets grandes),
usamos `pd.merge_asof`: un merge ordenado que para cada play encuentra
la sesion con `start_time <= played_at`. Luego filtramos los que superan `end_time`.

### Audio features en NULL

Con el endpoint restringido, `avg_bpm`, `avg_energy`, etc. son NULL.
Se guardan igualmente en `session_features` para cuando el endpoint
vuelva a estar disponible o se use una fuente alternativa.

---

## 3. label_activities.py — etiquetado heuristico

### Por que reglas y no ML desde el inicio

1. No hay datos suficientes para entrenar (50 plays = 4 sesiones)
2. Las reglas son auditables y explicables — sabes exactamente por que
   una sesion se etiqueto como "gimnasio"
3. Las reglas generan el dataset de entrenamiento para ML en fase 2

### Sistema de confidence scores

Cada regla suma puntos por condicion cumplida (total posible = 1.0).
Se elige la regla con mayor score. Si ninguna supera 0.4 → "desconocido".

```python
def rule_gimnasio(row):
    score = 0.0
    if 40 <= row["duration_minutes"] <= 100:  score += 0.4  # condicion principal
    if row["n_skips"] <= 2:                    score += 0.3  # musica continua
    if row["day_of_week"] in [0,1,2,3,4]:     score += 0.15 # entre semana
    if row["hour_of_day"] in [5..8, 17..20]:  score += 0.15 # horario gym
    return score
```

El score no es una probabilidad estadistica — es una medida de cuantas
condiciones se cumplen. Con mas datos, se puede reemplazar con un clasificador
que si produzca probabilidades reales.

### Limitacion actual: moto vs ducha

Con solo patrones temporales, sesiones cortas (< 15 min) sin skips pueden
ser ducha O moto. La diferencia real seria: BPM alto + energia alta para ducha,
variabilidad de BPM para moto. Sin audio features, ambas se etiquetan como moto
porque esa regla tiene mayor score promedio.

Cuando llegue el historial extendido (30 dias), los patrones recurrentes
(misma hora, mismo dia de semana) permitiran distinguirlas mejor.

---

## El orquestador run_pipeline.py

Ejecuta los 6 pasos en orden. Caracteristicas clave:

- `--from N`: permite empezar desde el paso N. Util para reejecutar solo
  la transformacion sin volver a llamar la API de Spotify.
- Si un paso falla, el pipeline se detiene — no escribe resultados parciales.
- Mide el tiempo de cada paso: util para identificar cuellos de botella.

```bash
python scripts/run_pipeline.py          # pipeline completo
python scripts/run_pipeline.py --from 4 # solo transformacion
```

---

## Flujo de datos completo

```
Spotify API
    ↓ ingest_plays.py
raw_plays (50 filas)
    ↓ ingest_audio_features.py
raw_audio_features (50 filas, features en NULL por restriccion API)
    ↓ ingest_artists.py
raw_artists (33 filas, genres en NULL por restriccion API)
    ↓ build_sessions.py
sessions (4 sesiones agrupadas por gap < 30 min)
    ↓ compute_features.py
session_features (4 registros: n_skips calculado, audio features NULL)
    ↓ label_activities.py
activity_labels (4 etiquetas: moto, moto, gimnasio, descanso)
```
