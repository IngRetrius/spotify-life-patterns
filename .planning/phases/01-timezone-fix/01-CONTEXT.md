# Phase 1: Timezone Fix - Context

**Gathered:** 2026-04-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Commitear el fix de timezone en `transformation/build_sessions.py` (ya existe sin commitear) y actualizar las filas existentes en la tabla `sessions` para que `hour_of_day` y `day_of_week` reflejen hora local de Bogotá (America/Bogota, UTC-5) en vez de UTC. Verificar que el fix es correcto via SQL query + revisión visual en el dashboard.

</domain>

<decisions>
## Implementation Decisions

### Re-run Strategy
- **D-01:** Ejecutar `python scripts/run_pipeline.py --from 4` para correr los pasos 4→6 (build_sessions → compute_features → label_activities). Esto corrige las horas Y recalcula features y labels con los datos corregidos. No toca ingestion (pasos 1-3).
- **D-02:** El upsert en `UPSERT_SESSION_SQL` ya usa `DO UPDATE SET hour_of_day = EXCLUDED.hour_of_day, day_of_week = EXCLUDED.day_of_week` — el re-run corrige automáticamente las filas existentes sin necesidad de DELETE ni migración SQL.

### Verificación
- **D-03:** Verificar con query SQL que compara `hour_of_day` vs `EXTRACT(HOUR FROM start_time AT TIME ZONE 'America/Bogota')` para detectar filas todavía desincronizadas.
- **D-04:** Verificar visualmente en el dashboard que la gráfica "Activity by Hour" muestra barras en horas coherentes con el comportamiento real del usuario.
- **D-05:** El PLAN.md debe incluir los comandos exactos (el `--from 4` y el query de verificación SQL) listos para copiar y correr.

### Claude's Discretion
- Formato exacto del query SQL de verificación — estructura a criterio del agente planificador.
- Si agregar o no un test unitario de `tz_convert` en `test_build_sessions.py` — fuera del scope elegido, el planificador puede incluirlo si es trivial.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Código con el fix
- `transformation/build_sessions.py` — Contiene el fix sin commitear: `start_local = start_time.tz_convert("America/Bogota")`, `hour_of_day: start_local.hour`, `day_of_week: start_local.dayofweek`, y el UPSERT con `DO UPDATE SET`. Leer el git diff para ver exactamente qué cambió.

### Orchestrator con --from flag
- `scripts/run_pipeline.py` — Soporta `--from N` para re-runs parciales. Verificar que `--from 4` corre los pasos 4, 5 y 6 en ese orden.

### Tests existentes
- `tests/test_build_sessions.py` — Contiene `TestAssignSessions` y `TestBuildSessionRecords`. El patrón `_plays()` factory y estructura de clases son el patrón a seguir si se agrega un test de timezone.

### Decisiones de arquitectura relevantes
- `docs/decisions/transformation_layer.md` — ADR con los 4 canonical sessions de producción y la lógica de heurísticas. Útil para entender qué valores de `hour_of_day` son esperados.
- `docs/decisions/db_design.md` — ADR con el diseño de la tabla `sessions`, incluyendo la estrategia de upsert idempotente.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `db/connection.py::get_connection()` — Conexión psycopg2 usada por todos los scripts de transformation. El re-run usa la misma conexión.
- `scripts/run_pipeline.py` — Flag `--from 4` ya implementado. Permite re-run desde cualquier paso sin modificar código.

### Established Patterns
- **Upsert idempotente:** Todos los pasos de transformation usan `ON CONFLICT ... DO UPDATE` o `DO NOTHING`. El re-run es siempre seguro.
- **Exit codes:** Los scripts llaman `sys.exit(1)` en error y retornan dict con stats en éxito. El orchestrator detecta SystemExit para marcar el paso como fallido.
- **Before/after row counts:** El orchestrator registra rows antes y después de cada paso. Los counts del re-run son observable en stdout.

### Integration Points
- La corrección en `sessions.hour_of_day` propaga automáticamente al dashboard via `load_activity_by_hour()` en `dashboard/queries.py` — esa query usa `s.hour_of_day` directamente de la tabla.
- `session_features` y `activity_labels` hacen JOIN con `sessions` por `session_id` — el re-run desde step 4 los recalcula con los datos corregidos.

</code_context>

<specifics>
## Specific Ideas

- El query de verificación debe comparar `hour_of_day` almacenado vs la conversión correcta en SQL:
  ```sql
  SELECT session_id, hour_of_day,
         EXTRACT(HOUR FROM start_time AT TIME ZONE 'America/Bogota')::int AS expected_hour,
         hour_of_day - EXTRACT(HOUR FROM start_time AT TIME ZONE 'America/Bogota')::int AS diff
  FROM sessions
  WHERE hour_of_day != EXTRACT(HOUR FROM start_time AT TIME ZONE 'America/Bogota')::int
  LIMIT 20;
  ```
  Después del re-run exitoso, este query debe retornar 0 filas.

</specifics>

<deferred>
## Deferred Ideas

- Agregar test unitario para `tz_convert` en `test_build_sessions.py` — evaluado como fuera del scope elegido. Candidato para Phase 2 o fase separada si el planificador lo considera trivial.

</deferred>

---

*Phase: 01-timezone-fix*
*Context gathered: 2026-04-15*
