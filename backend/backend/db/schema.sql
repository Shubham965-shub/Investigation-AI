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
    -- Real display name, not derived from username — added 2026-08-03 so the
    -- feedback service (a separate ARGUS Lighthouse app that reads this
    -- token's "name" claim to attribute submissions) shows a real name
    -- instead of a heuristic guess. NULL falls back to
    -- routers/auth.py's display_name_for_username() until backfilled.
    full_name TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Idempotent for the already-applied live table (2026-07-31) — ALTER, not
-- just the CREATE above, since that only fires on a fresh table.
ALTER TABLE athena_users ADD COLUMN IF NOT EXISTS full_name TEXT;

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

-- Added 2026-08-04, per the user: when RCI Plan Creation is accepted/approved
-- ("Accept and Push to TW" — routers/rci_plan.py's export_rci_plan), the
-- generated .docx is persisted here in addition to being downloaded to the
-- browser, as a frozen snapshot of exactly what was approved at that moment
-- (re-exporting after a later section edit produces a NEW row, not an
-- overwrite — this table is an append-only history, not a cache of "the
-- current export"). A separate downstream process (outside this backend)
-- is expected to poll push_status = 'pending' rows and push them into
-- Trackwise, then flip the status once done.
CREATE TABLE IF NOT EXISTS investigation_rci_plan_exports (
    id BIGSERIAL PRIMARY KEY,
    deviation_id INTEGER NOT NULL,
    docx BYTEA NOT NULL,
    truncated_sections INTEGER NOT NULL DEFAULT 0,
    approved_by INTEGER REFERENCES athena_users(id),
    push_status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_investigation_rci_plan_exports_deviation_id ON investigation_rci_plan_exports(deviation_id);
CREATE INDEX IF NOT EXISTS idx_investigation_rci_plan_exports_push_status ON investigation_rci_plan_exports(push_status);
