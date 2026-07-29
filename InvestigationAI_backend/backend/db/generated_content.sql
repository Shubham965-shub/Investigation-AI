-- Investigation AI — AI-generated content tables.
--
-- Sibling file to schema.sql (auth) and star_schema.sql (STAR schema decomposed
-- from the real Trackwise source table) — lives in the SAME shared Postgres
-- instance, NOT a separate database.
--
-- These tables hold the LLM-generated output for each investigation module
-- (problem statement, evidence, interview questionnaire, RCI plan), keyed by
-- deviation_id (the same identity as dim_event/fact_qms_event). Real
-- historical Trackwise fields come from the STAR schema tables; only the
-- generated output lives here. Read path is wired into the 4 GET endpoints;
-- write path (best-effort, non-blocking) is wired into the 4 POST endpoints
-- — but these tables have never been run against any real DB.
--
-- DO NOT RUN THIS AGAINST ANY DATABASE WITHOUT EXPLICIT APPROVAL — the user
-- verifies this with the DB owner first.

CREATE TABLE IF NOT EXISTS investigation_problem_statements (
    deviation_id INTEGER PRIMARY KEY REFERENCES dim_event(deviation_id),
    problem_statement TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS investigation_evidence_items (
    id SERIAL PRIMARY KEY,
    deviation_id INTEGER NOT NULL REFERENCES dim_event(deviation_id),
    description TEXT NOT NULL,
    is_checked BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_investigation_evidence_items_deviation_id ON investigation_evidence_items(deviation_id);

CREATE TABLE IF NOT EXISTS investigation_questionnaire_items (
    id SERIAL PRIMARY KEY,
    deviation_id INTEGER NOT NULL REFERENCES dim_event(deviation_id),
    description TEXT NOT NULL,
    is_checked BOOLEAN NOT NULL DEFAULT TRUE,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_investigation_questionnaire_items_deviation_id ON investigation_questionnaire_items(deviation_id);

CREATE TABLE IF NOT EXISTS investigation_rci_sections (
    id SERIAL PRIMARY KEY,
    deviation_id INTEGER NOT NULL REFERENCES dim_event(deviation_id),
    title TEXT NOT NULL,
    correlation TEXT,
    -- due_date/assignee: the approved Figma design shows both per section,
    -- but DS's RciPlanGenerateResponse doesn't return them yet (see project
    -- memory: rci-plan-schema-gap). Columns added now so this table doesn't
    -- need a migration once DS/frontend catch up — unused until then.
    due_date DATE,
    assignee TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_investigation_rci_sections_deviation_id ON investigation_rci_sections(deviation_id);

CREATE TABLE IF NOT EXISTS investigation_rci_tasks (
    id SERIAL PRIMARY KEY,
    section_id INTEGER NOT NULL REFERENCES investigation_rci_sections(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_investigation_rci_tasks_section_id ON investigation_rci_tasks(section_id);
