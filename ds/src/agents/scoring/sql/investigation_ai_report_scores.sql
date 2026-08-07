-- ============================================================================
-- Scoring RESULTS / evidence tables (public schema)
-- Database: investigation_ai   (server: azure_qa / qa-lighthouse-db)
--
-- Stores the audit trail for every scoring run — the "why" behind each mark:
--   * investigation_ai_report_score            — one row per scored report (summary + JSONB snapshot)
--   * investigation_ai_report_score_checkpoint — one row per checkpoint (verdict, marks, rationale, evidence)
--
-- persistence.py also creates these lazily (CREATE TABLE IF NOT EXISTS) on first
-- write, so applying this file is optional but keeps the schema explicit.
-- Idempotent: safe to re-run.
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.investigation_ai_report_score (
    id                      uuid PRIMARY KEY,
    created_at              timestamptz NOT NULL DEFAULT now(),
    filename                text,
    event_type              text,
    detected_sections       text[],
    score                   int,                -- headline integer shown to the FE
    overall_percentage      double precision,
    overall_marks           double precision,
    overall_max             double precision,
    task_report_percentage  double precision,   -- Report 1 (/40)
    iq_percentage           double precision,    -- Report 2 (/60)
    breakdown               jsonb NOT NULL        -- full response snapshot
);

CREATE TABLE IF NOT EXISTS public.investigation_ai_report_score_checkpoint (
    id              bigserial PRIMARY KEY,
    run_id          uuid NOT NULL REFERENCES public.investigation_ai_report_score(id) ON DELETE CASCADE,
    section         text NOT NULL,              -- task_report | rc | impact | capa
    checkpoint_id   text NOT NULL,              -- e.g. '3.1a', '1', '7.2'
    sub_criteria    text,
    checkpoint_text text,
    max_marks       numeric,
    verdict         text,                       -- Yes | No | NA | assignable | probable | none | level_1..level_5
    marks_awarded   numeric,
    applicable      boolean,
    rationale       text,                       -- why this verdict
    evidence_quote  text                        -- verbatim span from the report
);

CREATE INDEX IF NOT EXISTS ix_report_score_checkpoint_run
    ON public.investigation_ai_report_score_checkpoint(run_id);
