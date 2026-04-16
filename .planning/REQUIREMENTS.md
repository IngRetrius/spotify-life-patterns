# Requirements: Spotify Life Patterns — Timezone & Cache Fix

**Defined:** 2026-04-15
**Core Value:** El dashboard muestra los patrones de escucha reales — horas correctas (Bogotá), datos del pipeline más reciente.

## v1 Requirements

### Timezone Fix

- [ ] **TZ-01**: `hour_of_day` y `day_of_week` en tabla `sessions` almacenados en hora local (America/Bogota), no UTC
- [ ] **TZ-02**: El fix en `transformation/build_sessions.py` (tz_convert + DO UPDATE SET) commiteado al repo
- [ ] **TZ-03**: Las filas existentes en `sessions` corregidas via re-run de build_sessions (upsert idempotente actualiza las columnas)

### Cache

- [ ] **CACHE-01**: Los 8 decoradores `@st.cache_data(ttl=timedelta(hours=3))` en `dashboard/app.py` reducidos a `timedelta(minutes=30)`
- [ ] **CACHE-02**: El dashboard muestra datos del pipeline más reciente dentro de 30 minutos de cualquier run exitoso

## v2 Requirements

### Observabilidad

- **OBS-01**: Indicador visual en el dashboard de "Última actualización" (timestamp del dato más reciente)
- **OBS-02**: Botón de refresh manual para usuarios que quieren forzar recarga

## Out of Scope

| Feature | Reason |
|---------|--------|
| Botón de refresh manual v1 | TTL 30 min resuelve el problema; complejidad innecesaria ahora |
| Soporte multi-timezone | Siempre America/Bogota — un solo usuario |
| Migración SQL manual de horas | Re-run idempotente del pipeline es suficiente y más seguro |
| Cache invalidation en webhook | Overkill para un pipeline batch cada 6h |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| TZ-01 | Phase 1 | Pending |
| TZ-02 | Phase 1 | Pending |
| TZ-03 | Phase 1 | Pending |
| CACHE-01 | Phase 2 | Pending |
| CACHE-02 | Phase 2 | Pending |

**Coverage:**
- v1 requirements: 5 total
- Mapped to phases: 5
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-15*
*Last updated: 2026-04-15 after initial definition*
