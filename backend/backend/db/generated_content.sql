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

-- "Investigator-generated progress" (2026-09-21, per the user) — Action Center's progress bar
-- now tracks the LAST item generated/uploaded by a user holding the Investigator role
-- specifically, not just whoever happens to be logged in (Admin/SIT can generate on an
-- investigator's behalf, and that must not count toward this bar). Nullable: existing rows
-- predate this and carry no attribution. Read side: db/action_center_queries.py's
-- fetch_investigator_progress_stage(); write side: every generate/edit/upload endpoint across
-- these 7 tables now passes the calling user's id.
ALTER TABLE investigation_problem_statements ADD COLUMN IF NOT EXISTS generated_by INTEGER REFERENCES athena_users(id);
ALTER TABLE investigation_evidence_items ADD COLUMN IF NOT EXISTS generated_by INTEGER REFERENCES athena_users(id);
ALTER TABLE investigation_questionnaire_items ADD COLUMN IF NOT EXISTS generated_by INTEGER REFERENCES athena_users(id);
ALTER TABLE investigation_rci_sections ADD COLUMN IF NOT EXISTS generated_by INTEGER REFERENCES athena_users(id);
ALTER TABLE investigation_task_critique_reports ADD COLUMN IF NOT EXISTS uploaded_by INTEGER REFERENCES athena_users(id);
ALTER TABLE investigation_rc_capa_reports ADD COLUMN IF NOT EXISTS uploaded_by INTEGER REFERENCES athena_users(id);
ALTER TABLE investigation_rci_reports ADD COLUMN IF NOT EXISTS generated_by INTEGER REFERENCES athena_users(id);

-- Evidence Collection uncheck-cap fix (2026-09-22, per the user) — the "can't
-- deselect more than half" cap in EvidenceCollectionPage.tsx must stay pinned
-- to the ORIGINAL AI-generated item count regardless of items added later.
-- That distinction lived only in frontend session state (isUserAdded) and was
-- never persisted, so it silently reset to "everything is generated" on any
-- reload. Persisting it here is what makes the cap survive a reload/revisit.
ALTER TABLE investigation_evidence_items ADD COLUMN IF NOT EXISTS is_new BOOLEAN NOT NULL DEFAULT FALSE;

-- "What Was Enhanced" panel (2026-09-21, per the user) — a categorized diff
-- between the raw TrackWise description and the generated problem statement
-- (ds's POST /ps/v2/enhancements), so revisiting the page doesn't re-trigger
-- that LLM call. One row per deviation_id, upserted in place on regenerate —
-- same shape as investigation_problem_statements itself, just with the
-- output as a JSONB array instead of a single string (each element:
-- {category, tw_excerpt, llm_excerpt}). An empty array is a real,
-- successfully-generated "nothing meaningful found" result, distinct from
-- no row at all (never generated yet — frontend shows a "Generate" prompt).
CREATE TABLE IF NOT EXISTS investigation_problem_statement_enhancements (
    deviation_id INTEGER PRIMARY KEY REFERENCES dim_event(deviation_id),
    enhancements JSONB NOT NULL DEFAULT '[]'::jsonb,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- _llm duplicates (2026-09-23, per the user) of both problem-statement AI-generated-content
-- tables above — same columns, no data/read/write path pointed at them yet.
CREATE TABLE IF NOT EXISTS investigation_problem_statements_llm (
    deviation_id INTEGER PRIMARY KEY REFERENCES dim_event(deviation_id),
    problem_statement TEXT NOT NULL,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    generated_by INTEGER REFERENCES athena_users(id)
);

CREATE TABLE IF NOT EXISTS investigation_problem_statement_enhancements_llm (
    deviation_id INTEGER PRIMARY KEY REFERENCES dim_event(deviation_id),
    enhancements JSONB NOT NULL DEFAULT '[]'::jsonb,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- SIT Dashboard's "Remark" column (2026-09-11, per the user) — a free-text
-- note SITs use to track investigation activity, editable and visible to
-- the SIT role only (see routers/action_center.py's require_sit and the
-- remarks={} masking for non-SIT callers). One remark per TABLE ROW, not
-- per deviation_id — a deviation with multiple RCI IDs renders as multiple
-- rows (see ActionCenterPage.tsx's explodedInvestigations/composite-key
-- work, 2026-09-10) and each of those rows needs its own independent
-- remark, hence the (deviation_id, rci_id) composite key rather than
-- deviation_id alone. rci_id is nullable for the case where a row genuinely
-- has none — not assumed absent for any particular event type, just
-- possible in general (2026-09-11, per the user) — NULLS NOT DISTINCT
-- (PG16, confirmed live) makes that composite key behave as a real upsert
-- target even when rci_id is NULL, instead of every NULL row silently
-- comparing unequal to every other the way a plain UNIQUE would.
CREATE TABLE IF NOT EXISTS investigation_remarks (
    deviation_id INTEGER NOT NULL REFERENCES dim_event(deviation_id),
    rci_id TEXT,
    remark TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE NULLS NOT DISTINCT (deviation_id, rci_id)
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
    -- The real per-task {task_number, title, objective, findings, inference,
    -- section_labels} ds's extract_tasks step produced from the uploaded document
    -- (ds's TaskReportCritiqueResponse.task_evidence) — previously computed and
    -- then discarded before reaching this table entirely, leaving `summary`
    -- (a thin strengths-only blurb, one per report/section, not per task) as the
    -- only trace of the upload reaching RCI Report Section 5. Added 2026-08-25,
    -- per the user, so Section 5 can ground on the report's real findings/
    -- inference instead. Reset to '[]' on every re-upload, same as
    -- `recommendations` above.
    task_findings JSONB NOT NULL DEFAULT '[]'::jsonb,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (deviation_id, task_index)
);

CREATE INDEX IF NOT EXISTS idx_investigation_task_critique_reports_deviation_id ON investigation_task_critique_reports(deviation_id);

ALTER TABLE investigation_task_critique_reports ADD COLUMN IF NOT EXISTS task_findings JSONB NOT NULL DEFAULT '[]'::jsonb;

-- Asynchronous upload processing (2026-09-28, per the user) — task report / RC&CAPA report
-- uploads used to call DS's critique + scoring endpoints synchronously inside the request,
-- which risked Azure Container Apps' platform-level request timeout (240s default) killing the
-- connection before a slow-but-eventually-successful DS call ever returned (see
-- DS_SERVICE_HEAVY_READ_TIMEOUT_SECONDS in config/settings.py) — the browser then saw a raw
-- network failure with no error detail. Uploads now persist immediately with
-- critique_pending=TRUE and return right away; the actual DS calls run in the background
-- (routers/task_critique.py's _process_task_report_async), clearing this flag when done.
-- critique_state.py's compute_upload_state surfaces this as a new "processing" status.
ALTER TABLE investigation_task_critique_reports ADD COLUMN IF NOT EXISTS critique_pending BOOLEAN NOT NULL DEFAULT FALSE;

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
    -- Critique's task_score (2026-08-07, per the user). rc_score and
    -- impact_score were originally combined into one rc_score figure
    -- (matching this module's own "RC Impact Assessment Critique" category,
    -- which bundles the two together everywhere else) but ds genuinely
    -- scores them as two separate rubric sections, so they're shown as two
    -- separate figures now (2026-08-25, per the user) even though they still
    -- sit under that one shared category elsewhere in the module. capa_score
    -- is the CAPA section's percentage alone.
    rc_score INTEGER,
    impact_score INTEGER,
    capa_score INTEGER,
    -- Consolidated figure (2026-08-07, per the user): rc_score's, impact_score's,
    -- and capa_score's underlying raw marks added together, divided by their
    -- combined max — not a naive average of the three percentages.
    total_score INTEGER,
    -- Same as investigation_task_critique_reports.score_breakdown — ds's full
    -- /score/report `info` breakdown table(s) (rc + impact + capa sections
    -- all present here, unlike Task Critique's single task_report section),
    -- stored verbatim as a JSON array.
    score_breakdown JSONB,
    -- The real per-section content ds's extract_rci_report_sections already computes
    -- deterministically (no LLM) from the uploaded document, but which — until 2026-08-25 —
    -- never left ds: only rc_summary/capa_summary (LLM-condensed 3-4 sentence blurbs) ever
    -- reached this table. Added so RCI Report generation (Root Cause Conclusion, Impact
    -- Assessment, Correction/Remedial Action, CAPA) can ground on the uploaded RC & CAPA
    -- document's own text/structure instead of thin summaries or TrackWise fields. Same
    -- "surface what was already being discarded" pattern as
    -- investigation_task_critique_reports.task_findings.
    rc_conclusion_text_raw TEXT,
    is_repeat_occurrence BOOLEAN,
    impact_assessment_text TEXT,
    -- The "Conclusion:"/"Disposition:" line onward within impact_assessment_text above —
    -- an additive subset of it (2026-09-01, per the user), not a replacement, so RCI
    -- Report generation can source Impact Assessment's `conclusion` field verbatim from
    -- it instead of LLM-synthesizing it (mirrors correction_remedial_text's sole-sourcing
    -- pattern below).
    impact_conclusion_text TEXT,
    correction_remedial_text TEXT,
    capa_text_raw TEXT,
    capa_items JSONB NOT NULL DEFAULT '[]'::jsonb,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_investigation_rc_capa_reports_deviation_id ON investigation_rc_capa_reports(deviation_id);

ALTER TABLE investigation_rc_capa_reports ADD COLUMN IF NOT EXISTS rc_conclusion_text_raw TEXT;
ALTER TABLE investigation_rc_capa_reports ADD COLUMN IF NOT EXISTS is_repeat_occurrence BOOLEAN;
ALTER TABLE investigation_rc_capa_reports ADD COLUMN IF NOT EXISTS impact_assessment_text TEXT;
ALTER TABLE investigation_rc_capa_reports ADD COLUMN IF NOT EXISTS impact_conclusion_text TEXT;
ALTER TABLE investigation_rc_capa_reports ADD COLUMN IF NOT EXISTS correction_remedial_text TEXT;
ALTER TABLE investigation_rc_capa_reports ADD COLUMN IF NOT EXISTS capa_text_raw TEXT;
ALTER TABLE investigation_rc_capa_reports ADD COLUMN IF NOT EXISTS capa_items JSONB NOT NULL DEFAULT '[]'::jsonb;

-- Asynchronous upload processing — same reasoning/pattern as
-- investigation_task_critique_reports.critique_pending above.
ALTER TABLE investigation_rc_capa_reports ADD COLUMN IF NOT EXISTS critique_pending BOOLEAN NOT NULL DEFAULT FALSE;

-- Without this, a background DS failure during async upload processing (see
-- routers/rc_capa_critique.py's _process_rc_capa_report_async) has no way to signal "critiqued
-- but failed" — the report is left with empty recommendations, which compute_upload_state
-- (db/critique_state.py) reads as "DS genuinely found nothing to flag" and locks as complete
-- with no reupload allowed. That's a real regression from the old synchronous design (a failed
-- request consumed nothing and could be retried immediately). Adding this column makes
-- critique_state.py's existing critique_failed branch reachable for RC & CAPA too, matching
-- Task Critique's behavior exactly (doesn't lock, allows an immediate reupload).
ALTER TABLE investigation_rc_capa_reports ADD COLUMN IF NOT EXISTS critique_failed BOOLEAN NOT NULL DEFAULT FALSE;

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

-- Composite (deviation_id, rci_id) key groundwork (2026-09-25, per the user) — some OOS/OOT
-- deviations ("Phase 2", per the functional team) have TWO RCIs opened simultaneously against
-- the same deviation, each needing its own fully independent workflow through every module
-- below. rci_id is TEXT (matches fact_qms_event.rci_key cast to string, same convention
-- investigation_remarks already established) and nullable — the vast majority of deviations
-- have 0 or 1 RCI and keep working identically, since NULLS NOT DISTINCT treats every existing
-- NULL-rci_id row as continuing to upsert onto itself exactly as before.
--
-- Three different existing key shapes needed three different treatments (constraint names
-- below confirmed live via pg_constraint, not guessed defaults):
--
-- Shape A — single deviation_id PK (dropped in favor of a composite unique, deviation_id stays
-- NOT NULL and FK'd, just no longer the sole key):
ALTER TABLE investigation_problem_statements DROP CONSTRAINT investigation_problem_statements_pkey;
ALTER TABLE investigation_problem_statements ADD COLUMN IF NOT EXISTS rci_id TEXT;
ALTER TABLE investigation_problem_statements ADD CONSTRAINT investigation_problem_statements_devrci_key UNIQUE NULLS NOT DISTINCT (deviation_id, rci_id);

ALTER TABLE investigation_problem_statement_enhancements DROP CONSTRAINT investigation_problem_statement_enhancements_pkey;
ALTER TABLE investigation_problem_statement_enhancements ADD COLUMN IF NOT EXISTS rci_id TEXT;
ALTER TABLE investigation_problem_statement_enhancements ADD CONSTRAINT investigation_problem_statement_enhancements_devrci_key UNIQUE NULLS NOT DISTINCT (deviation_id, rci_id);

ALTER TABLE investigation_rci_reports DROP CONSTRAINT investigation_rci_reports_pkey;
ALTER TABLE investigation_rci_reports ADD COLUMN IF NOT EXISTS rci_id TEXT;
ALTER TABLE investigation_rci_reports ADD CONSTRAINT investigation_rci_reports_devrci_key UNIQUE NULLS NOT DISTINCT (deviation_id, rci_id);

-- Shape B — surrogate id PK, no per-set uniqueness (these are lists, scoped by the
-- DELETE-then-INSERT replace_* pattern, not ON CONFLICT — no UNIQUE needed, just the column
-- and an index that includes it). investigation_rci_tasks needs NO change: it has no
-- deviation_id column at all, purely FK'd via section_id ON DELETE CASCADE — once sections
-- carry rci_id, tasks inherit scoping transitively through their parent section row.
ALTER TABLE investigation_evidence_items ADD COLUMN IF NOT EXISTS rci_id TEXT;
DROP INDEX IF EXISTS idx_investigation_evidence_items_deviation_id;
CREATE INDEX IF NOT EXISTS idx_investigation_evidence_items_dev_rci ON investigation_evidence_items(deviation_id, rci_id);

ALTER TABLE investigation_questionnaire_items ADD COLUMN IF NOT EXISTS rci_id TEXT;
DROP INDEX IF EXISTS idx_investigation_questionnaire_items_deviation_id;
CREATE INDEX IF NOT EXISTS idx_investigation_questionnaire_items_dev_rci ON investigation_questionnaire_items(deviation_id, rci_id);

ALTER TABLE investigation_rci_sections ADD COLUMN IF NOT EXISTS rci_id TEXT;
DROP INDEX IF EXISTS idx_investigation_rci_sections_deviation_id;
CREATE INDEX IF NOT EXISTS idx_investigation_rci_sections_dev_rci ON investigation_rci_sections(deviation_id, rci_id);

-- Shape C — existing 2-column UNIQUE, extended to 3/4 columns:
ALTER TABLE investigation_task_critique_reports ADD COLUMN IF NOT EXISTS rci_id TEXT;
ALTER TABLE investigation_task_critique_reports DROP CONSTRAINT investigation_task_critique_reports_deviation_task_uniq;
ALTER TABLE investigation_task_critique_reports ADD CONSTRAINT investigation_task_critique_reports_devrci_task_key UNIQUE NULLS NOT DISTINCT (deviation_id, rci_id, task_index);

ALTER TABLE investigation_task_critique_recommendation_history ADD COLUMN IF NOT EXISTS rci_id TEXT;
ALTER TABLE investigation_task_critique_recommendation_history DROP CONSTRAINT investigation_task_critique_r_deviation_id_task_index_attem_key;
ALTER TABLE investigation_task_critique_recommendation_history ADD CONSTRAINT investigation_task_critique_recommendation_history_devrci_key UNIQUE NULLS NOT DISTINCT (deviation_id, rci_id, task_index, attempt_number);

-- investigation_rc_capa_reports — confirmed live: no unique constraint exists at all today
-- (attempt_number is a plain append-only counter, "latest" picked in Python), just add the
-- column and extend the lookup index.
ALTER TABLE investigation_rc_capa_reports ADD COLUMN IF NOT EXISTS rci_id TEXT;
DROP INDEX IF EXISTS idx_investigation_rc_capa_reports_deviation_id;
CREATE INDEX IF NOT EXISTS idx_investigation_rc_capa_reports_dev_rci ON investigation_rc_capa_reports(deviation_id, rci_id, attempt_number);

-- Deliberately NOT migrated: investigation_problem_statements_llm /
-- investigation_problem_statement_enhancements_llm — confirmed zero read/write path anywhere
-- in the codebase; migrating dead tables adds untested-DDL risk for no behavioral benefit.
