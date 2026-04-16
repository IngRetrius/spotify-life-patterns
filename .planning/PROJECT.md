# Spotify Life Patterns — Bugfix: Timezone & Cache

## What This Is

Dashboard de Spotify que extrae plays via API, construye sesiones de escucha, infiere actividades (gym, shower, tasks, casual) con heurísticas, y las visualiza en Streamlit. El pipeline corre en GitHub Actions cada 6 horas. Este milestone cubre dos bugs de correctitud: horas incorrectas en la tabla `sessions` (UTC en vez de UTC-5 Bogotá) y un TTL de cache demasiado largo que impide ver datos frescos al recargar el dashboard.

## Core Value

El dashboard debe mostrar los patrones de escucha reales del usuario — horas y actividades correctas, datos del pipeline más reciente.

## Requirements

### Validated

- ✓ Pipeline ETL 6 pasos (ingest → transform → label) — existente
- ✓ Sesiones detectadas con gap de 30 min — existente
- ✓ Actividades etiquetadas (shower/gym/tasks/casual) — existente
- ✓ Dashboard Streamlit con KPIs, gráficas, tabla de sesiones — existente
- ✓ Pipeline en GitHub Actions (cron 6h) — existente
- ✓ Timestamps de plays convertidos a America/Bogota en SQL — existente

### Active

- [ ] `hour_of_day` y `day_of_week` en tabla `sessions` en hora local Bogotá (UTC-5), no UTC
- [ ] Filas existentes en DB actualizadas con horas correctas (re-run build_sessions)
- [ ] TTL de `@st.cache_data` reducido a 30 min en todos los decoradores del dashboard
- [ ] `build_sessions.py` con la corrección de timezone commiteado

### Out of Scope

- Agregar botón de refresh manual — la reducción de TTL es suficiente
- Cambiar timezone del usuario (siempre America/Bogota)
- Migración SQL para actualizar las filas — el re-run idempotente del pipeline es suficiente

## Context

**Bug de timezone:** `build_sessions.py` usaba `start_time.hour` (UTC) para `hour_of_day`. La corrección (`start_time.tz_convert("America/Bogota").hour`) ya está en el archivo pero sin commitear. El UPSERT fue actualizado de `DO NOTHING` a `DO UPDATE SET hour_of_day = EXCLUDED.hour_of_day` para que el re-run corrija las filas existentes.

**Bug de cache:** El dashboard tiene 8 decoradores `@st.cache_data(ttl=timedelta(hours=3))` en `app.py`. Con la app en Streamlit Cloud y el pipeline corriendo cada 6h, los datos pueden estar desactualizados hasta 3 horas después de un run exitoso. Reducir a 30 min alinea mejor el refresh con la frecuencia del pipeline.

## Constraints

- **Tech**: Python 3.12, pandas, Streamlit 1.40.2, Supabase/PostgreSQL
- **No DB migration**: El fix de timezone se aplica via re-run del pipeline (upsert idempotente)
- **No downtime**: `DO UPDATE SET` permite actualizar en producción sin borrar filas

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Re-run pipeline para corregir horas | El upsert `DO UPDATE SET` ya maneja el update, cero código extra | — Pending |
| TTL 30 min en vez de 60 | La app hiberna tras inactividad; 30 min garantiza datos frescos al despertar | — Pending |
| No botón de refresh manual | Complejidad innecesaria — TTL reducido resuelve el problema | — Pending |

---

## Evolution

Este documento evoluciona en transiciones de fase y milestones.

**Después de cada fase:**
1. ¿Requisitos invalidados? → Mover a Out of Scope con razón
2. ¿Requisitos validados? → Mover a Validated con referencia de fase
3. ¿Nuevos requisitos emergieron? → Agregar a Active
4. ¿Decisiones a registrar? → Agregar a Key Decisions
5. ¿"What This Is" sigue siendo preciso? → Actualizar si drifteó

**Después de cada milestone:**
1. Revisión completa de todas las secciones
2. Core Value check — ¿sigue siendo la prioridad correcta?
3. Auditar Out of Scope — ¿las razones siguen siendo válidas?
4. Actualizar Context con el estado actual

---
*Last updated: 2026-04-15 after initialization*
