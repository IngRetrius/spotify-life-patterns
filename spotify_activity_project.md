# Proyecto: Detector de Actividades con Spotify

## Objetivo del proyecto

Construir un pipeline de datos end-to-end que analice el historial de reproduccion de Spotify para **inferir actividades de vida diaria** (ducha, gimnasio, moto, trabajo, descanso) basandose en patrones de escucha, audio features y horarios.

El proposito es doble:
1. Obtener insights personales reales sobre habitos y rutinas
2. Servir como proyecto de portfolio para roles de **Data Engineer** o **Data Architect**

---

## Perfil del desarrollador

- Rol objetivo: Data Engineer / Data Architect
- Nivel: en desarrollo / construyendo portfolio
- Ubicacion: Colombia
- Herramientas con las que esta familiarizado: por definir en sesion
- Preferencia de entorno: local primero, nube como extension opcional

---

## Fuente de datos principal

**Spotify API** via la libreria `spotipy` en Python.

Datos disponibles:
- Historial reciente de reproduccion (ultimo 50 tracks via API en tiempo real)
- Historial extendido (solicitud manual a Spotify, archivo JSON, hasta 1 ano)
- Audio Features por cancion:
  - `tempo` — BPM de la cancion
  - `energy` — intensidad y actividad percibida (0 a 1)
  - `danceability` — que tan bailable es (0 a 1)
  - `valence` — positividad emocional (0 a 1)
  - `acousticness` — presencia de instrumentos acusticos (0 a 1)
  - `instrumentalness` — ausencia de voz (0 a 1)
  - `loudness` — volumen promedio en dB
  - `speechiness` — presencia de palabras habladas (0 a 1)
- Metadata de cancion: nombre, artista, album, duracion, genero (via artist endpoint)

---

## Logica de negocio: actividades a detectar

Cada actividad tiene un perfil esperado basado en señales implicitas:

### Ducha
- Duracion de sesion: 5 a 15 minutos
- Sin pausas (el usuario no puede interactuar con el telefono)
- Horario tipico: 6am-9am o 9pm-11pm
- Audio: energia alta, BPM elevado, pop o reggaeton

### Gimnasio
- Duracion: 45 a 90 minutos
- Pocas o ninguna pausa larga
- BPM alto y consistente (120-180)
- Generos: reggaeton, electronica, rap energico
- Dias recurrentes y horarios fijos (habito)

### Moto
- Sesion continua sin pausas
- Duracion variable (trayectos)
- Cualquier hora del dia
- Posible cruce con Google Maps Timeline para validar movimiento

### Trabajo / Concentracion
- Sesiones largas: 2 a 4 horas
- Musica instrumental, lo-fi, ambient, o mismo playlist en loop
- Horario: 8am a 6pm en dias de semana
- `instrumentalness` y `acousticness` altos

### Descanso / Noche
- Horario: 10pm a 1am
- BPM bajo, energia baja
- Musica tranquila, acustica, emotional

---

## Definicion tecnica de "sesion"

Una sesion es un bloque continuo de reproducciones donde el gap entre el fin de una cancion y el inicio de la siguiente es menor a **30 minutos**.

Atributos calculados por sesion:
- `session_id`
- `start_time`, `end_time`
- `duration_minutes`
- `n_tracks` — cantidad de canciones
- `n_skips` — canciones saltadas antes del 50% de duracion
- `avg_bpm`, `avg_energy`, `avg_valence`, `avg_danceability`
- `dominant_genre` — genero mas frecuente en la sesion
- `hour_of_day`, `day_of_week`
- `activity_label` — etiqueta inferida (ducha, gym, moto, trabajo, descanso, desconocido)

---

## Arquitectura objetivo

```
Spotify API
     |
  Ingesta (Python + spotipy)
  - Pull de historial reciente (polling cada X horas via cron o Airflow)
  - Enriquecimiento con Audio Features
     |
  Raw Layer
  - SQLite (local, rapido para empezar)
  - Tablas: raw_plays, raw_audio_features, raw_artists
     |
  Transformacion (Python / dbt)
  - Construccion de sesiones
  - Calculo de features por sesion
  - Etiquetado con reglas heuristicas
     |
  Analytics Layer
  - Tablas: sessions, session_features, activity_labels
     |
  Modelo (opcional fase 2)
  - K-Means clustering para descubrir patrones
  - Clasificacion supervisada si hay etiquetas manuales
     |
  Visualizacion
  - Streamlit (preferido para portfolio)
  - O Metabase / Power BI conectado a SQLite/Postgres
```

---

## Stack tecnologico definido

| Capa | Tecnologia | Notas |
|---|---|---|
| Lenguaje | Python 3.10+ | |
| Acceso API | spotipy | Libreria oficial de Spotify para Python |
| Almacenamiento | SQLite (fase 1) | Migrar a Postgres en fase 2 si se necesita |
| Transformacion | pandas + SQL | dbt opcional en fase 2 |
| Orquestacion | cron / scripts manuales (fase 1) | Airflow o Prefect en fase 2 |
| Visualizacion | Streamlit | |
| Control de version | Git + GitHub | README con decisiones de arquitectura |
| Entorno | Local | GCP o AWS free tier como extension |

---

## Estado actual del proyecto

- [ ] Crear app en developer.spotify.com
- [ ] Configurar credenciales (CLIENT_ID, CLIENT_SECRET, REDIRECT_URI)
- [ ] Script de ingesta: historial reciente
- [ ] Script de enriquecimiento: audio features
- [ ] Diseño de esquema de base de datos (SQLite)
- [ ] Logica de construccion de sesiones
- [ ] Reglas heuristicas de etiquetado de actividades
- [ ] Dashboard en Streamlit
- [ ] README con documentacion de arquitectura
- [ ] (Opcional) Modelo de clustering

---

## Consideraciones importantes

- La API de Spotify solo retorna los **ultimos 50 tracks** en tiempo real. Para historial largo es necesario solicitar los datos directamente a Spotify (proceso tarda 5-30 dias).
- Los Audio Features endpoint (`/audio-features`) puede ser deprecado o limitado en cuentas nuevas segun cambios recientes de Spotify. Verificar disponibilidad al inicio.
- El etiquetado de actividades es **inferido**, no confirmado. La precision dependera de la consistencia de los habitos del usuario.
- Todo el dato es personal y sensible. No subir credenciales ni datos personales al repositorio de GitHub. Usar `.env` y `.gitignore` desde el inicio.

---

## Instrucciones para el agente

Cuando trabajemos en este proyecto:

1. Siempre preguntar en que fase o componente estamos trabajando antes de generar codigo
2. Priorizar codigo modular y legible sobre codigo compacto
3. Incluir manejo de errores desde el principio (rate limits de API, datos nulos, duplicados)
4. Documentar cada funcion con docstrings breves
5. Recordar que el objetivo final es un portfolio: el codigo debe verse profesional en GitHub
6. Si hay decisiones de arquitectura, explicar el razonamiento (eso es lo que evaluan los reclutadores)
7. Usar este archivo como fuente de verdad del proyecto. Si algo cambia, actualizar aqui primero.
