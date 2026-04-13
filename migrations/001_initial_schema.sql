-- Migration: 001_initial_schema
-- Description: Raw layer (raw_plays, raw_audio_features, raw_artists)
--              + Analytics layer (sessions, session_features, activity_labels)
--              + Indexes para queries frecuentes del pipeline y dashboard

-- ── RAW LAYER ────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS raw_plays (
    id          UUID        DEFAULT gen_random_uuid() PRIMARY KEY,
    track_id    TEXT        NOT NULL,
    track_name  TEXT        NOT NULL,
    artist_id   TEXT        NOT NULL,
    artist_name TEXT        NOT NULL,
    album_name  TEXT,
    duration_ms INTEGER,
    played_at   TIMESTAMPTZ NOT NULL,
    inserted_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (track_id, played_at)
);

CREATE TABLE IF NOT EXISTS raw_audio_features (
    track_id            TEXT    PRIMARY KEY,
    tempo               FLOAT,
    energy              FLOAT,
    danceability        FLOAT,
    valence             FLOAT,
    acousticness        FLOAT,
    instrumentalness    FLOAT,
    loudness            FLOAT,
    speechiness         FLOAT,
    liveness            FLOAT,
    duration_ms         INTEGER,
    inserted_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS raw_artists (
    artist_id   TEXT    PRIMARY KEY,
    name        TEXT    NOT NULL,
    genres      TEXT[],
    popularity  INTEGER,
    inserted_at TIMESTAMPTZ DEFAULT NOW()
);

-- ── ANALYTICS LAYER ──────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS sessions (
    session_id          UUID    DEFAULT gen_random_uuid() PRIMARY KEY,
    start_time          TIMESTAMPTZ NOT NULL,
    end_time            TIMESTAMPTZ NOT NULL,
    duration_minutes    FLOAT   NOT NULL,
    n_tracks            INTEGER,
    hour_of_day         INTEGER,
    day_of_week         INTEGER,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS session_features (
    session_id          UUID    REFERENCES sessions(session_id) ON DELETE CASCADE PRIMARY KEY,
    avg_bpm             FLOAT,
    avg_energy          FLOAT,
    avg_valence         FLOAT,
    avg_danceability    FLOAT,
    avg_acousticness    FLOAT,
    avg_loudness        FLOAT,
    n_skips             INTEGER,
    dominant_genre      TEXT,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS activity_labels (
    session_id          UUID    REFERENCES sessions(session_id) ON DELETE CASCADE PRIMARY KEY,
    activity_label      TEXT    NOT NULL,
    confidence_score    FLOAT,
    labeling_method     TEXT    DEFAULT 'heuristic',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

-- ── ÍNDICES ──────────────────────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_raw_plays_played_at   ON raw_plays (played_at DESC);
CREATE INDEX IF NOT EXISTS idx_raw_plays_track_id    ON raw_plays (track_id);
CREATE INDEX IF NOT EXISTS idx_sessions_start_time   ON sessions  (start_time DESC);
CREATE INDEX IF NOT EXISTS idx_activity_labels_label ON activity_labels (activity_label);
