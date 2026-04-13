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

### Por que 3 actividades (no 5)

El diseno original tenia 5 reglas: ducha, gimnasio, moto, trabajo, descanso.
El problema: sin audio features, moto y trabajo son indistinguibles solo
por duracion y hora. Una sesion de 103 minutos a las 3am se etiquetaba
como "moto" cuando claramente es estudio nocturno.

Decision: reducir a 3 actividades con senales temporales claras y mutuamente
exclusivas:

| Actividad | Senal dominante          | Diferenciador de hora        |
|-----------|--------------------------|------------------------------|
| ducha     | Duracion muy corta 5-20m | Manana (6-10h) o noche (20-23h) |
| gimnasio  | Duracion 35-110m         | Dia/tarde (5-10h o 16-22h)   |
| tareas    | Duracion > 40m           | Madrugada (0-5h o 22-23h)    |

El bonus de hora es el discriminador clave: gimnasio y tareas pueden
durar lo mismo (60-90 min), pero el gym no ocurre a las 3am.

### Sistema de confidence scores

Cada regla suma puntos por condicion cumplida (total posible = 1.0).
Se elige la regla con mayor score. Si ninguna supera 0.4 → "desconocido".

```python
SHOWER_HOURS      = set(range(6, 11))  | set(range(20, 24))   # 6-10h y 20-23h
GYM_HOURS         = set(range(5, 11))  | set(range(16, 23))   # 5-10h y 16-22h
NIGHT_STUDY_HOURS = set(range(22, 24)) | set(range(0, 6))     # 22-23h y 0-5h

def rule_ducha(row):     # max 0.5 + 0.3 + 0.2 = 1.0
    if 5 <= duration <= 20:        score += 0.5  # condicion principal
    if n_skips == 0:               score += 0.3  # no puede tocar el telefono
    if hour in SHOWER_HOURS:       score += 0.2  # horario tipico de aseo

def rule_gimnasio(row):  # max 0.4 + 0.3 + 0.3 = 1.0
    if 35 <= duration <= 110:      score += 0.4  # duracion tipica
    if n_skips <= 2:               score += 0.3  # musica continua
    if hour in GYM_HOURS:          score += 0.3  # 5-10am o 4-10pm

def rule_tareas(row):    # max 0.5 + 0.2 + 0.3 = 1.0
    if duration > 40:              score += 0.5  # sesion larga
    if n_skips <= 5:               score += 0.2  # musica de fondo
    if hour in NIGHT_STUDY_HOURS:  score += 0.3  # madrugada = estudio
```

Resultados con las 4 sesiones actuales:

| Sesion       | Dur    | Hora | Skips | Etiqueta  | Score |
|--------------|--------|------|-------|-----------|-------|
| 38e0b333...  | 103.5m | 3h   | 0     | tareas    | 1.00  |
| 74ca3bf1...  | 14.5m  | 17h  | 0     | ducha     | 0.80  |
| 44158cee...  | 62.3m  | 20h  | 2     | gimnasio  | 1.00  |
| 83e34a9d...  | 2.6m   | 23h  | 0     | ducha     | 0.50  |

El score no es una probabilidad estadistica — es una medida de cuantas
condiciones se cumplen. Con mas datos, se puede reemplazar con un clasificador
que si produzca probabilidades reales.

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
