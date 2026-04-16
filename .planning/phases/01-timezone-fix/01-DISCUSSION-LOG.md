# Phase 1: Timezone Fix - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-15
**Phase:** 01-timezone-fix
**Areas discussed:** Re-run strategy, Verificación

---

## Re-run Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| `python scripts/run_pipeline.py --from 4` | Corre pasos 4–6. Corrige horas Y recalcula features/labels. No toca ingestion. | ✓ |
| `python transformation/build_sessions.py` directo | Solo actualiza sessions. Deja session_features y activity_labels del run anterior. | |
| `python scripts/run_pipeline.py` completo | Pipeline completo desde paso 1. Requiere OAuth activo. Innecesario para este fix. | |

**User's choice:** `python scripts/run_pipeline.py --from 4`
**Notes:** El upsert con DO UPDATE SET ya maneja la corrección de filas existentes sin necesidad de DELETE ni migración.

---

## Verificación

| Option | Description | Selected |
|--------|-------------|----------|
| Query SQL + visual en dashboard | Query compara hour_of_day vs EXTRACT(HOUR ... AT TIME ZONE 'America/Bogota'). Luego revisar Activity by Hour chart. | ✓ |
| Solo visual en dashboard | Revisar barras del chart en horas coherentes con comportamiento real. | |
| Solo query SQL | Confirmar en DB sin abrir el dashboard. | |

**User's choice:** Query SQL + visual en dashboard
**Notes:** El plan debe incluir los comandos exactos (--from 4 y query SQL de verificación) listos para copiar y correr.

### Quién ejecuta

| Option | Description | Selected |
|--------|-------------|----------|
| Comandos exactos en el plan | PLAN.md documenta el comando y el query listos para copiar y correr. | ✓ |
| GitHub Actions manual trigger | Disparar workflow desde GitHub (corre pipeline completo, incluye ingestion). | |

**User's choice:** El plan incluye los comandos exactos.

---

## Claude's Discretion

- Formato exacto del query SQL de verificación
- Decisión sobre si agregar test unitario de `tz_convert` (evaluado fuera del scope elegido)

## Deferred Ideas

- Test unitario para `tz_convert` en `test_build_sessions.py` — no seleccionado como área a discutir, puede incluirse si el planificador lo considera trivial
