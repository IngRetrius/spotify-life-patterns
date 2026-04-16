# Roadmap: Spotify Life Patterns — Timezone & Cache Fix

## Overview

Two focused bugfixes to restore correctness to the dashboard: first, commit and apply the timezone fix so session hours reflect Bogota local time; second, reduce cache TTL so the dashboard shows pipeline output within 30 minutes of any run.

## Phases

- [ ] **Phase 1: Timezone Fix** - Commit tz_convert correction and verify DB rows update to local hours
- [ ] **Phase 2: Cache TTL Reduction** - Reduce all 8 @st.cache_data decorators from 3h to 30min

## Phase Details

### Phase 1: Timezone Fix
**Goal**: Session hours in the database reflect America/Bogota local time, not UTC
**Depends on**: Nothing (first phase)
**Requirements**: TZ-01, TZ-02, TZ-03
**Success Criteria** (what must be TRUE):
  1. `transformation/build_sessions.py` is committed with `tz_convert("America/Bogota").hour` for `hour_of_day` and `day_of_week`
  2. The UPSERT uses `DO UPDATE SET hour_of_day = EXCLUDED.hour_of_day, day_of_week = EXCLUDED.day_of_week` so a re-run corrects existing rows
  3. After re-running build_sessions, `hour_of_day` values in the `sessions` table match Bogota local clock (UTC-5), not UTC
**Plans**: TBD

### Phase 2: Cache TTL Reduction
**Goal**: Dashboard queries always reflect data from the most recent pipeline run within 30 minutes
**Depends on**: Phase 1
**Requirements**: CACHE-01, CACHE-02
**Success Criteria** (what must be TRUE):
  1. All 8 `@st.cache_data` decorators in `dashboard/app.py` use `ttl=timedelta(minutes=30)`
  2. After a pipeline run completes, the dashboard shows updated data within 30 minutes of reloading
**Plans**: TBD

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Timezone Fix | 0/? | Not started | - |
| 2. Cache TTL Reduction | 0/? | Not started | - |
