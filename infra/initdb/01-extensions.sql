-- Runs once, on first boot of an empty db_data volume.
-- Schema itself is owned by backend/migrations/, applied by `make migrate`.
CREATE EXTENSION IF NOT EXISTS vector;
