-- Auth bootstrap schema for this backend, in the SAME shared Postgres
-- instance as InvestigationAi_DS (confirmed — not a separate database).
-- The STAR schema (FACT_QMS_EVENTS + dimensions) lives alongside these
-- tables in star_schema.sql — a sibling file, not a replacement for this one.
--
-- Applied to the live shared DB on 2026-07-31 (explicit user approval) —
-- routers/auth.py now verifies real bcrypt-hashed athena_users rows and
-- issues JWTs from them; the fact_qms_event-style FK typos (roles/users
-- instead of athena_roles/athena_users) were fixed before running this.

CREATE TABLE IF NOT EXISTS athena_roles (
    id SERIAL PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS athena_users (
    id SERIAL PRIMARY KEY,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role_id INTEGER REFERENCES athena_roles(id),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS athena_api_call_trails (
    id BIGSERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES athena_users(id),
    method TEXT NOT NULL,
    path TEXT NOT NULL,
    status_code INTEGER,
    duration_ms INTEGER,
    ip_address TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_api_call_trails_user_id ON athena_api_call_trails(user_id);
CREATE INDEX IF NOT EXISTS idx_api_call_trails_created_at ON athena_api_call_trails(created_at);
