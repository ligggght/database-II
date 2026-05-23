-- =============================================================================
-- Schema do benchmark — MySQL (InnoDB)
-- -----------------------------------------------------------------------------
-- Equivalente ao schema do PostgreSQL, com tipos ajustados para MySQL.
-- Mesmas decisões de design (id manual, release_date como texto, idempotente).
-- ENGINE=InnoDB é o padrão no MySQL 8+, mas explicitamos para deixar claro.
-- =============================================================================

CREATE TABLE IF NOT EXISTS albums (
    id                INT            PRIMARY KEY,
    position          INT,
    release_name      VARCHAR(500),
    artist_name       VARCHAR(500),
    release_date      VARCHAR(50),
    release_type      VARCHAR(50),
    primary_genres    TEXT,
    secondary_genres  TEXT,
    descriptors       TEXT,
    avg_rating        DECIMAL(5,2),
    rating_count      INT,
    review_count      INT
) ENGINE=InnoDB;
