-- Migration: 002_add_country_to_raw_plays
-- Description: Agrega conn_country a raw_plays para almacenar el pais
--              desde el que se reprodujo cada track (codigo ISO alpha-2).
--              El historial exportado de Spotify incluye este campo; la
--              ingesta via API no lo expone, por eso la columna es nullable.

ALTER TABLE raw_plays
    ADD COLUMN IF NOT EXISTS conn_country TEXT;
