-- =============================================================================
-- Schema do benchmark — PostgreSQL
-- -----------------------------------------------------------------------------
-- Tabela 'albums' baseada no dataset RYM Top 5000.
--
-- Decisões:
--   * O 'id' é fornecido explicitamente pelo script (sem SERIAL / IDENTITY),
--     para que as inserções fiquem IDÊNTICAS entre Postgres, MySQL e SQLite
--     e a comparação seja justa.
--   * 'release_date' é VARCHAR (e não DATE) porque o CSV tem datas mal
--     formatadas em alguns registros — guardar como texto evita erros de
--     parsing durante o INSERT.
--   * IF NOT EXISTS torna o script idempotente: subir o container de novo
--     não dá erro se a tabela já existir.
-- =============================================================================

CREATE TABLE IF NOT EXISTS albums (
    id                INTEGER       PRIMARY KEY,
    position          INTEGER,
    release_name      VARCHAR(500),
    artist_name       VARCHAR(500),
    release_date      VARCHAR(50),
    release_type      VARCHAR(50),
    primary_genres    TEXT,
    secondary_genres  TEXT,
    descriptors       TEXT,
    avg_rating        NUMERIC(5,2),
    rating_count      INTEGER,
    review_count      INTEGER
);
