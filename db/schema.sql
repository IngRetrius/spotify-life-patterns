-- ============================================================
-- SCHEMA — Spotify Activity Detector
-- ============================================================
-- Convención de nombres:
--   raw_*   → datos tal como vienen de la API (Bronze layer)
--   sessions, session_features, activity_labels → datos procesados (Silver/Gold)
--
-- Ejecutar este archivo una vez en Supabase SQL Editor para crear las tablas.
-- ============================================================


-- ── RAW LAYER ────────────────────────────────────────────────────────────────

-- Historial de reproducciones
CREATE TABLE IF NOT EXISTS raw_plays (
    id              UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    track_id        TEXT        NOT NULL,
    track_name      TEXT        NOT NULL,
    artist_id       TEXT        NOT NULL,
    artist_name     TEXT        NOT NULL,
    album_name      TEXT,
    duration_ms     INTEGER,
    played_at       TIMESTAMPTZ NOT NULL,
    inserted_at     TIMESTAMPTZ DEFAULT NOW(),

    -- Evita duplicados si el cron corre más de una vez en la misma ventana
    UNIQUE (track_id, played_at)
);

-- Audio features por canción (se enriquece una vez por track_id único)
CREATE TABLE IF NOT EXISTS raw_audio_features (
    track_id            TEXT    PRIMARY KEY,
    tempo               FLOAT,   -- BPM
    energy              FLOAT,   -- 0 a 1, intensidad percibida
    danceability        FLOAT,   -- 0 a 1
    valence             FLOAT,   -- 0 a 1, positividad emocional
    acousticness        FLOAT,   -- 0 a 1
    instrumentalness    FLOAT,   -- 0 a 1, ausencia de voz
    loudness            FLOAT,   -- dB promedio (valores negativos)
    speechiness         FLOAT,   -- 0 a 1, presencia de palabras habladas
    liveness            FLOAT,   -- 0 a 1, probabilidad de ser en vivo
    duration_ms         INTEGER,
    inserted_at         TIMESTAMPTZ DEFAULT NOW()
);

-- Metadata de artistas (géneros son clave para el etiquetado)
CREATE TABLE IF NOT EXISTS raw_artists (
    artist_id   TEXT    PRIMARY KEY,
    name        TEXT    NOT NULL,
    genres      TEXT[], -- array de strings, e.g. ["reggaeton", "latin pop"]
    popularity  INTEGER,
    inserted_at TIMESTAMPTZ DEFAULT NOW()
);


-- ── ANALYTICS LAYER ──────────────────────────────────────────────────────────

-- Una fila por bloque continuo de escucha (gap < 30 min entre canciones)
CREATE TABLE IF NOT EXISTS sessions (
    session_id      UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    start_time      TIMESTAMPTZ NOT NULL,
    end_time        TIMESTAMPTZ NOT NULL,
    duration_minutes FLOAT      NOT NULL,
    n_tracks        INTEGER,
    hour_of_day     INTEGER,    -- 0-23, hora de inicio de sesión
    day_of_week     INTEGER,    -- 0=lunes, 6=domingo (convencion Python)
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Indicadores agregados de la sesión (calculados desde raw_audio_features)
CREATE TABLE IF NOT EXISTS session_features (
    session_id          UUID    REFERENCES sessions(session_id) ON DELETE CASCADE PRIMARY KEY,
    avg_bpm             FLOAT,
    avg_energy          FLOAT,
    avg_valence         FLOAT,
    avg_danceability    FLOAT,
    avg_acousticness    FLOAT,
    avg_loudness        FLOAT,
    n_skips             INTEGER, -- canciones escuchadas menos del 50% de su duración
    dominant_genre      TEXT,    -- género más frecuente en la sesión
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- Etiqueta de actividad inferida por sesión
CREATE TABLE IF NOT EXISTS activity_labels (
    session_id          UUID    REFERENCES sessions(session_id) ON DELETE CASCADE PRIMARY KEY,
    activity_label      TEXT    NOT NULL, -- 'ducha', 'gimnasio', 'moto', 'trabajo', 'descanso', 'desconocido'
    confidence_score    FLOAT,            -- 0 a 1, qué tan segura es la inferencia
    labeling_method     TEXT    DEFAULT 'heuristic', -- 'heuristic' o 'ml' en fase 2
    created_at          TIMESTAMPTZ DEFAULT NOW()
);


-- ── ÍNDICES ──────────────────────────────────────────────────────────────────
-- Aceleran las consultas más frecuentes del pipeline y el dashboard

CREATE INDEX IF NOT EXISTS idx_raw_plays_played_at   ON raw_plays (played_at DESC);
CREATE INDEX IF NOT EXISTS idx_raw_plays_track_id    ON raw_plays (track_id);
CREATE INDEX IF NOT EXISTS idx_sessions_start_time   ON sessions  (start_time DESC);
CREATE INDEX IF NOT EXISTS idx_activity_labels_label ON activity_labels (activity_label);
