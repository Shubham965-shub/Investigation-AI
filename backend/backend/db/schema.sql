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

-- Set on every successful POST /auth/login (routers/auth.py) — backs the
-- User Management page's "Last Logged In" column (2026-09-08, per the user).
-- NULL for an account that has never logged in yet.
ALTER TABLE athena_users ADD COLUMN IF NOT EXISTS last_login TIMESTAMPTZ;

-- New "Investigator" role (2026-09-09, per the user) — scoped so a signed-in
-- Investigator only ever sees their OWN investigations in Action Center
-- (routers/action_center.py's get_action_center_summary filters by this
-- BEFORE any KPI/status-card/chart aggregation, so every derived number is
-- scoped too, not just the table). Admin/User/SIT are unaffected — the
-- scoping only activates when "Investigator" is in the JWT's roles claim.
INSERT INTO athena_roles (name, description)
VALUES ('Investigator', 'Can only view their own investigations in Action Center')
ON CONFLICT (name) DO NOTHING;

-- The "hook" linking an athena_users row to its real-world identity in the
-- star schema (dim_investigator.investigator is a free-text name, not an
-- FK-able id — there's no shared identity between the two systems). Set by
-- an admin via User Management when creating/editing an Investigator-role
-- user. When left NULL, action_center.py falls back to matching against the
-- token's own `name` claim (athena_users.full_name) instead — works
-- automatically whenever the account's full_name already matches
-- dim_investigator.investigator verbatim, with this column as the explicit
-- override for the cases where it doesn't (nicknames, formatting mismatches,
-- etc).
ALTER TABLE athena_users ADD COLUMN IF NOT EXISTS investigator_name TEXT;

-- New "CXO" role (2026-09-09, per the user) — reserved now for the upcoming
-- CXO Dashboard (a new page, investigated from Figma but not yet built).
-- No route/endpoint checks this role yet; added ahead of the build purely so
-- it's assignable via User Management already. When the dashboard itself is
-- built, its route/endpoint(s) must gate on "CXO" in the JWT's roles claim,
-- same require_admin-style pattern already used for the admin-only User
-- Management endpoints.
INSERT INTO athena_roles (name, description)
VALUES ('CXO', 'Executive role — will be scoped to the CXO Dashboard only once built')
ON CONFLICT (name) DO NOTHING;

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

-- Added 2026-08-25, per the user: same append-only snapshot convention as
-- investigation_rci_plan_exports above, for the RCI Report module's own
-- "Accept and Push to TW" (routers/rci_report.py's export_rci_report).
CREATE TABLE IF NOT EXISTS investigation_rci_report_exports (
    id BIGSERIAL PRIMARY KEY,
    deviation_id INTEGER NOT NULL,
    docx BYTEA NOT NULL,
    approved_by INTEGER REFERENCES athena_users(id),
    push_status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_investigation_rci_report_exports_deviation_id ON investigation_rci_report_exports(deviation_id);
CREATE INDEX IF NOT EXISTS idx_investigation_rci_report_exports_push_status ON investigation_rci_report_exports(push_status);

-- Added 2026-08-06, per the user: RC & CAPA Critique's "Accept and Push for
-- SIT Review" action currently just persists the locked report's file bytes
-- here as a frozen approval snapshot — same append-only convention as
-- investigation_rci_plan_exports above. There is no real external SIT
-- review integration yet (and no defined mechanism for one to actually
-- complete), so `status` only ever reaches 'pending' for now — this table
-- exists purely so the button's action has somewhere real to write to.
-- NOT YET RUN AGAINST THE LIVE DB — needs the same explicit approval this
-- file's other tables got before being applied.
CREATE TABLE IF NOT EXISTS investigation_rc_capa_sit_reviews (
    id BIGSERIAL PRIMARY KEY,
    deviation_id INTEGER NOT NULL,
    docx BYTEA NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    approved_by INTEGER REFERENCES athena_users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_investigation_rc_capa_sit_reviews_deviation_id ON investigation_rc_capa_sit_reviews(deviation_id);

-- Added 2026-08-06, per the user: Task Critique reads the RCI Plan document
-- generated by module 4 (investigation_rci_plan_exports.docx, above) to get
-- its task list — parsed in Python via services/rci_plan_extraction.py, not
-- ds (ds's own POST /critique/extract expects a differently-structured
-- document and fails against our real template). If no export exists yet
-- for an investigation, this table holds a manually-uploaded stand-in
-- document instead, parsed the same way. One row per investigation —
-- re-uploading replaces the prior stand-in (UNIQUE(deviation_id) + upsert).
-- NOT YET RUN AGAINST THE LIVE DB — needs the same explicit approval this
-- file's other tables got before being applied.
CREATE TABLE IF NOT EXISTS investigation_task_critique_source_documents (
    id BIGSERIAL PRIMARY KEY,
    deviation_id INTEGER NOT NULL UNIQUE,
    file_name TEXT NOT NULL,
    docx BYTEA NOT NULL,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
