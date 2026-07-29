-- Auth bootstrap schema for this backend, in the SAME shared Postgres
-- instance as InvestigationAi_DS (confirmed — not a separate database).
-- The STAR schema (FACT_QMS_EVENTS + dimensions) lives alongside these
-- tables in star_schema.sql — a sibling file, not a replacement for this one.
--
-- Row population (creating actual user accounts, roles) happens outside
-- this codebase.
--
-- DO NOT RUN THIS AGAINST ANY DATABASE WITHOUT EXPLICIT APPROVAL — the user
-- verifies this with the DB owner first.

CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role_id INTEGER REFERENCES roles(id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS api_call_trails (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    status_code INTEGER,
    duration_ms INTEGER,
    ip_address TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_api_call_trails_user_id ON api_call_trails(user_id);
CREATE INDEX IF NOT EXISTS idx_api_call_trails_created_at ON api_call_trails(created_at);
