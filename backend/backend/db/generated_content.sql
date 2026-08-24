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
    -- 6M fishbone category (MATERIAL/METHOD/MACHINE/MEASUREMENT/MAN/ENVIRONMENT).
    -- Column added 2026-08-24, then superseded the same day: the bucket is
    -- now baked directly into `title` (e.g. "MATERIAL: Section Title") by
    -- ds/src/agents/rci_plan/nodes.py, since RciSectionItem/the frontend
    -- only ever render `title` — avoids a frontend change to surface it.
    -- Left in place, unpopulated, rather than run another live migration to
    -- drop it.
    six_m_bucket TEXT,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Whole-section include/exclude from the final plan (2026-08-20, per the
-- user) — same "checked = keep it" convention investigation_rci_tasks'
-- is_checked already uses per-subtask, just at the section level. Excluded
-- sections are skipped entirely by build_rci_plan_docx, same as an
-- unchecked task is skipped from a section's details cell.
ALTER TABLE investigation_rci_sections ADD COLUMN IF NOT EXISTS is_checked BOOLEAN NOT NULL DEFAULT TRUE;

CREATE INDEX IF NOT EXISTS idx_investigation_rci_sections_deviation_id ON investigation_rci_sections(deviation_id);

CREATE TABLE IF NOT EXISTS investigation_rci_tasks (
    id SERIAL PRIMARY KEY,
    section_id INTEGER NOT NULL REFERENCES investigation_rci_sections(id) ON DELETE CASCADE,
    description TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_investigation_rci_tasks_section_id ON investigation_rci_tasks(section_id);

-- Task Critique (module step 5) — each task is one block extracted from the
-- RCI Plan document (services/rci_plan_extraction.py — see
-- investigation_task_critique_source_documents in schema.sql for where that
-- document comes from). Not keyed by investigation_rci_sections.id anymore
-- (2026-08-06, per the user) — that table isn't populated by anything real
-- right now (RCI Plan Creation's own persistence into it depends on this
-- same file being run, which it hasn't been), so Task Critique's own tasks
-- are identified by their position in the extracted list instead
-- (task_index, 0-based, stable as long as the same source document is used).
-- A task can be uploaded/reuploaded up to 3 times (attempt_number); only the
-- latest attempt is ever kept — each new upload REPLACES this row in place
-- (per the user, 2026-08-06: no need to retain previous/rejected attempts'
-- files or critiques, only the current/final state). attempt_number is an
-- explicit counter (not derived from row count, since there's only ever one
-- row per task) so the 3-upload cap still works. is_gospel marks a report
-- that was uploaded after every recommendation on the prior attempt was
-- rejected — that report skips critique entirely and locks the task
-- immediately (per the user, 2026-08-05). Recommendations are stored inline
-- as a JSONB array (each element: {id, description, decision, reason,
-- decided_at}) rather than a child table, since there's no cross-attempt
-- history to normalize anymore and the list is always small. Status/lock/
-- upload-count are derived in Python from this row (see
-- db/task_critique_queries.py's compute_section_state), never stored
-- redundantly here.
CREATE TABLE IF NOT EXISTS investigation_task_critique_reports (
    id SERIAL PRIMARY KEY,
    deviation_id INTEGER NOT NULL REFERENCES dim_event(deviation_id),
    task_index INTEGER NOT NULL,
    attempt_number INTEGER NOT NULL DEFAULT 1,
    file_name TEXT NOT NULL,
    file_bytes BYTEA NOT NULL,
    is_gospel BOOLEAN NOT NULL DEFAULT FALSE,
    summary TEXT,
    task_score INTEGER,
    recommendations JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- True when ds's critique came back degenerate — total_tasks_analyzed=0,
    -- meaning it couldn't find any real tasks to review at all (e.g. the
    -- uploaded file passed the local format check — see
    -- services/task_report_format.py — but still wasn't a genuine task
    -- report, or ds's task extraction itself failed). Uploads that trigger
    -- this are now rejected outright before persisting (2026-08-13, per the
    -- user), so this only ever gets set on rows from before that check
    -- existed — surfaced on the list page as the same error state.
    critique_failed BOOLEAN NOT NULL DEFAULT FALSE,
    -- Full per-checkpoint breakdown table(s) from ds's /score/report response
    -- (its `info` field — see ds/src/agents/scoring/api/schemas.py's InfoTable/
    -- InfoRow) — a JSON array, stored verbatim, set alongside task_score
    -- whenever it's set (2026-08-14, per the user: shown via a small info
    -- icon next to the score).
    score_breakdown JSONB,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (deviation_id, task_index)
);

CREATE INDEX IF NOT EXISTS idx_investigation_task_critique_reports_deviation_id ON investigation_task_critique_reports(deviation_id);

-- Append-only audit log of every attempt's generated recommendation set
-- (2026-08-07, per the user) — investigation_task_critique_reports above
-- only ever holds the CURRENT attempt (replaced in place), so without this,
-- attempt 1's and 2's recommendations are gone the moment attempt 2/3 is
-- uploaded. One row per (deviation_id, task_index, attempt_number); never
-- updated after insert. Not read by compute_section_state or any live
-- business rule — purely a history/audit trail alongside the report row.
CREATE TABLE IF NOT EXISTS investigation_task_critique_recommendation_history (
    id BIGSERIAL PRIMARY KEY,
    deviation_id INTEGER NOT NULL REFERENCES dim_event(deviation_id),
    task_index INTEGER NOT NULL,
    attempt_number INTEGER NOT NULL,
    summary TEXT,
    recommendations JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (deviation_id, task_index, attempt_number)
);

-- RC & CAPA Critique (module step 6) — one shared upload cycle for the whole
-- investigation (not per-RCI-section like Task Critique). Each uploaded
-- report is critiqued into two fixed categories (rc_impact/capa) by ds's
-- POST /critique/analyse-task-report. Same 3-upload-cap + all-rejected-means-
-- next-upload-is-gospel rule as Task Critique (per the user, 2026-08-06) —
-- see db/critique_state.py's compute_upload_state, shared by both modules.
-- Never replaced in place — each upload is a fresh INSERT, so every
-- attempt's row (and its recommendations) is naturally kept, unlike Task
-- Critique's single upserted row. Each category's summary/strengths/
-- recommendations live directly on this row as separate rc_*/capa_* columns
-- (2026-08-07, per the user: match Task Critique's "one row, recommendations
-- as an inline JSONB array" shape) rather than normalized child tables —
-- recommendation element shape is identical to Task Critique's ({id,
-- description, decision, reason, decided_at}), except ids are only unique
-- per report, not globally: rc_recommendations run 0..len(rc)-1,
-- capa_recommendations continue numbering from there (see
-- rc_capa_critique_queries.py's save_critiques/set_recommendation_decision).
CREATE TABLE IF NOT EXISTS investigation_rc_capa_reports (
    id SERIAL PRIMARY KEY,
    deviation_id INTEGER NOT NULL REFERENCES dim_event(deviation_id),
    attempt_number INTEGER NOT NULL,
    file_name TEXT NOT NULL,
    file_bytes BYTEA NOT NULL,
    is_gospel BOOLEAN NOT NULL DEFAULT FALSE,
    rc_summary TEXT,
    rc_strengths TEXT,
    rc_recommendations JSONB NOT NULL DEFAULT '[]'::jsonb,
    capa_summary TEXT,
    capa_strengths TEXT,
    capa_recommendations JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- ds's rubric-based /score/report, as percentages — set once this report
    -- becomes final (gospel or 3rd attempt), same trigger/pattern as Task
    -- Critique's task_score (2026-08-07, per the user). rc_score is the
    -- combined Root Cause + Impact sections' percentage (matches this
    -- module's own "RC Impact Assessment Critique" category, which already
    -- bundles the two together everywhere else); capa_score is the CAPA
    -- section's percentage alone. Column names/split match a table already
    -- created directly against the live DB before this code existed.
    rc_score INTEGER,
    capa_score INTEGER,
    -- Consolidated figure (2026-08-07, per the user): rc_score's and
    -- capa_score's underlying raw marks added together, divided by their
    -- combined max — not a naive average of the two percentages.
    total_score INTEGER,
    -- Same as investigation_task_critique_reports.score_breakdown — ds's full
    -- /score/report `info` breakdown table(s) (rc + impact + capa sections
    -- all present here, unlike Task Critique's single task_report section),
    -- stored verbatim as a JSON array.
    score_breakdown JSONB,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_investigation_rc_capa_reports_deviation_id ON investigation_rc_capa_reports(deviation_id);

-- RCI Report (module step 7 of 7) — one row per investigation, upserted in
-- place on regenerate (2026-08-21, per the user: no "attempt" concept in
-- this module's UI, unlike Task Critique/RC & CAPA, so no history table).
-- report is the full 11-section RciReportSections payload (see
-- schemas/rci_report.py), stored as one JSONB blob rather than normalized
-- into columns — the same convention investigation_problem_statements uses,
-- just for a much larger nested shape. mc_confirmed/manual_entries persist
-- across regenerations so the investigator doesn't have to re-enter them
-- every time; both are inputs to ds's POST /rci-report/generate, not
-- generated output.
CREATE TABLE IF NOT EXISTS investigation_rci_reports (
    deviation_id INTEGER PRIMARY KEY REFERENCES dim_event(deviation_id),
    report JSONB,
    mc_confirmed BOOLEAN,
    manual_entries JSONB NOT NULL DEFAULT '{}'::jsonb,
    generated_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
