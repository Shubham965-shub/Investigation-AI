-- ============================================================================
-- Scoring checklist tables (public schema)
-- Database: investigation_ai   (server: azure_qa / qa-lighthouse-db)
--
-- Holds the marking checklists used to score investigation reports:
--   * Task Report Execution rubric  (/40)
--   * IQ Score rubric — RC (/30), Impact (/10), CAPA (/20)  → /60
--
-- Tables live in the public schema, prefixed with investigation_ai_ (moved out of
-- the former dedicated task_report_critique schema, which is dropped below).
--
-- GENERATED from src/agents/scoring/rubric/rubric_config.py — do not edit by hand.
-- Regenerate: uv run python -m src.agents.scoring.sql.generate_checklist_seed
-- Idempotent: safe to re-run (ON CONFLICT DO UPDATE keeps the DB in sync with code).
-- ============================================================================

-- Remove the previous dedicated schema (its tables are relocated below).
DROP SCHEMA IF EXISTS task_report_critique CASCADE;

CREATE TABLE IF NOT EXISTS public.investigation_ai_checklist_section (
    section         text PRIMARY KEY,          -- task_report | rc | impact | capa
    label           text        NOT NULL,
    native_max      numeric     NOT NULL,       -- section total as printed on the source checklist
    achievable_max  numeric     NOT NULL,       -- sum of checkpoint maxima (max earnable)
    source          text        NOT NULL,       -- originating checklist file
    display_order   int         NOT NULL
);

CREATE TABLE IF NOT EXISTS public.investigation_ai_checklist_checkpoint (
    section         text        NOT NULL REFERENCES public.investigation_ai_checklist_section(section) ON DELETE CASCADE,
    checkpoint_id   text        NOT NULL,        -- e.g. '6.1a', '1'
    sub_criteria    text        NOT NULL,
    checkpoint_text text        NOT NULL,
    max_marks       numeric     NOT NULL,        -- marks awarded when satisfied
    kind            text        NOT NULL DEFAULT 'binary',   -- binary | classification
    allow_na        boolean     NOT NULL DEFAULT false,
    tiers           jsonb,                        -- null unless kind='classification' (e.g. RC tiers)
    display_order   int         NOT NULL,
    PRIMARY KEY (section, checkpoint_id)
);

-- These tables are a code-generated mirror of rubric_config.py — clear and
-- reload so removed/renamed checkpoints never linger as stale rows.
DELETE FROM public.investigation_ai_checklist_checkpoint;
DELETE FROM public.investigation_ai_checklist_section;


-- ── Sections ────────────────────────────────────────────────────────────────
INSERT INTO public.investigation_ai_checklist_section (section, label, native_max, achievable_max, source, display_order) VALUES
    ('task_report', 'Task Report Execution', 40.0, 40.0, 'Task_Report_Execution_Rubric_40marks.docx', 1)
ON CONFLICT (section) DO UPDATE SET
    label = EXCLUDED.label, native_max = EXCLUDED.native_max,
    achievable_max = EXCLUDED.achievable_max, source = EXCLUDED.source,
    display_order = EXCLUDED.display_order;
INSERT INTO public.investigation_ai_checklist_section (section, label, native_max, achievable_max, source, display_order) VALUES
    ('rc', 'Root Cause / Probable Causes', 30.0, 30.0, 'IQ _ RC ,IMPACT & CAPA .xlsx', 2)
ON CONFLICT (section) DO UPDATE SET
    label = EXCLUDED.label, native_max = EXCLUDED.native_max,
    achievable_max = EXCLUDED.achievable_max, source = EXCLUDED.source,
    display_order = EXCLUDED.display_order;
INSERT INTO public.investigation_ai_checklist_section (section, label, native_max, achievable_max, source, display_order) VALUES
    ('impact', 'Final Impact Assessment', 10.0, 10.0, 'IQ _ RC ,IMPACT & CAPA .xlsx', 3)
ON CONFLICT (section) DO UPDATE SET
    label = EXCLUDED.label, native_max = EXCLUDED.native_max,
    achievable_max = EXCLUDED.achievable_max, source = EXCLUDED.source,
    display_order = EXCLUDED.display_order;
INSERT INTO public.investigation_ai_checklist_section (section, label, native_max, achievable_max, source, display_order) VALUES
    ('capa', 'Effectiveness of Corrections and CAPA', 20.0, 20.0, 'IQ _ RC ,IMPACT & CAPA .xlsx', 4)
ON CONFLICT (section) DO UPDATE SET
    label = EXCLUDED.label, native_max = EXCLUDED.native_max,
    achievable_max = EXCLUDED.achievable_max, source = EXCLUDED.source,
    display_order = EXCLUDED.display_order;

-- ── Checkpoints ─────────────────────────────────────────────────────────────
INSERT INTO public.investigation_ai_checklist_checkpoint (section, checkpoint_id, sub_criteria, checkpoint_text, max_marks, kind, allow_na, tiers, display_order) VALUES
    ('task_report', '1', '2.2 Title & Objective Quality', 'Title is clear and specific. It states what is being investigated.', 4.0, 'binary', false, NULL, 1)
ON CONFLICT (section, checkpoint_id) DO UPDATE SET
    sub_criteria = EXCLUDED.sub_criteria, checkpoint_text = EXCLUDED.checkpoint_text,
    max_marks = EXCLUDED.max_marks, kind = EXCLUDED.kind, allow_na = EXCLUDED.allow_na,
    tiers = EXCLUDED.tiers, display_order = EXCLUDED.display_order;
INSERT INTO public.investigation_ai_checklist_checkpoint (section, checkpoint_id, sub_criteria, checkpoint_text, max_marks, kind, allow_na, tiers, display_order) VALUES
    ('task_report', '2', '2.2 Title & Objective Quality', 'Each task states a specific, answerable Objective linked to the problem / a hypothesis.', 4.0, 'binary', false, NULL, 2)
ON CONFLICT (section, checkpoint_id) DO UPDATE SET
    sub_criteria = EXCLUDED.sub_criteria, checkpoint_text = EXCLUDED.checkpoint_text,
    max_marks = EXCLUDED.max_marks, kind = EXCLUDED.kind, allow_na = EXCLUDED.allow_na,
    tiers = EXCLUDED.tiers, display_order = EXCLUDED.display_order;
INSERT INTO public.investigation_ai_checklist_checkpoint (section, checkpoint_id, sub_criteria, checkpoint_text, max_marks, kind, allow_na, tiers, display_order) VALUES
    ('task_report', '3', '3.1 Evidence & Objectivity', 'Findings are supported by objective evidence and data (batch records, logbooks, trend data, interviews, reconstruction).', 6.0, 'binary', false, NULL, 3)
ON CONFLICT (section, checkpoint_id) DO UPDATE SET
    sub_criteria = EXCLUDED.sub_criteria, checkpoint_text = EXCLUDED.checkpoint_text,
    max_marks = EXCLUDED.max_marks, kind = EXCLUDED.kind, allow_na = EXCLUDED.allow_na,
    tiers = EXCLUDED.tiers, display_order = EXCLUDED.display_order;
INSERT INTO public.investigation_ai_checklist_checkpoint (section, checkpoint_id, sub_criteria, checkpoint_text, max_marks, kind, allow_na, tiers, display_order) VALUES
    ('task_report', '4', '3.1 Evidence & Objectivity', 'Evidence both for and against is recorded. No cherry-picking. Findings state facts and are quantified where relevant.', 4.0, 'binary', false, NULL, 4)
ON CONFLICT (section, checkpoint_id) DO UPDATE SET
    sub_criteria = EXCLUDED.sub_criteria, checkpoint_text = EXCLUDED.checkpoint_text,
    max_marks = EXCLUDED.max_marks, kind = EXCLUDED.kind, allow_na = EXCLUDED.allow_na,
    tiers = EXCLUDED.tiers, display_order = EXCLUDED.display_order;
INSERT INTO public.investigation_ai_checklist_checkpoint (section, checkpoint_id, sub_criteria, checkpoint_text, max_marks, kind, allow_na, tiers, display_order) VALUES
    ('task_report', '5', '3.2 Completeness & Traceability', 'Every part of the task is completed. Any gap is declared, not left open.', 4.0, 'binary', false, NULL, 5)
ON CONFLICT (section, checkpoint_id) DO UPDATE SET
    sub_criteria = EXCLUDED.sub_criteria, checkpoint_text = EXCLUDED.checkpoint_text,
    max_marks = EXCLUDED.max_marks, kind = EXCLUDED.kind, allow_na = EXCLUDED.allow_na,
    tiers = EXCLUDED.tiers, display_order = EXCLUDED.display_order;
INSERT INTO public.investigation_ai_checklist_checkpoint (section, checkpoint_id, sub_criteria, checkpoint_text, max_marks, kind, allow_na, tiers, display_order) VALUES
    ('task_report', '6', '3.2 Completeness & Traceability', 'All data in the Findings can be traced to a source.', 6.0, 'binary', false, NULL, 6)
ON CONFLICT (section, checkpoint_id) DO UPDATE SET
    sub_criteria = EXCLUDED.sub_criteria, checkpoint_text = EXCLUDED.checkpoint_text,
    max_marks = EXCLUDED.max_marks, kind = EXCLUDED.kind, allow_na = EXCLUDED.allow_na,
    tiers = EXCLUDED.tiers, display_order = EXCLUDED.display_order;
INSERT INTO public.investigation_ai_checklist_checkpoint (section, checkpoint_id, sub_criteria, checkpoint_text, max_marks, kind, allow_na, tiers, display_order) VALUES
    ('task_report', '7', '4.1 Logical Linkage & Analytical Depth', 'Inference follows logically from that task''s findings. No unsupported conclusions.', 4.0, 'binary', false, NULL, 7)
ON CONFLICT (section, checkpoint_id) DO UPDATE SET
    sub_criteria = EXCLUDED.sub_criteria, checkpoint_text = EXCLUDED.checkpoint_text,
    max_marks = EXCLUDED.max_marks, kind = EXCLUDED.kind, allow_na = EXCLUDED.allow_na,
    tiers = EXCLUDED.tiers, display_order = EXCLUDED.display_order;
INSERT INTO public.investigation_ai_checklist_checkpoint (section, checkpoint_id, sub_criteria, checkpoint_text, max_marks, kind, allow_na, tiers, display_order) VALUES
    ('task_report', '8', '4.1 Logical Linkage & Analytical Depth', 'Ruled-out causes are justified by the findings. Listed factors are examined (mark NA if not applicable).', 4.0, 'binary', true, NULL, 8)
ON CONFLICT (section, checkpoint_id) DO UPDATE SET
    sub_criteria = EXCLUDED.sub_criteria, checkpoint_text = EXCLUDED.checkpoint_text,
    max_marks = EXCLUDED.max_marks, kind = EXCLUDED.kind, allow_na = EXCLUDED.allow_na,
    tiers = EXCLUDED.tiers, display_order = EXCLUDED.display_order;
INSERT INTO public.investigation_ai_checklist_checkpoint (section, checkpoint_id, sub_criteria, checkpoint_text, max_marks, kind, allow_na, tiers, display_order) VALUES
    ('task_report', '9', '4.1 Logical Linkage & Analytical Depth', 'All inferences together give a complete, gap-free basis for the root cause. This is explained clearly even if the inference is no root cause.', 4.0, 'binary', false, NULL, 9)
ON CONFLICT (section, checkpoint_id) DO UPDATE SET
    sub_criteria = EXCLUDED.sub_criteria, checkpoint_text = EXCLUDED.checkpoint_text,
    max_marks = EXCLUDED.max_marks, kind = EXCLUDED.kind, allow_na = EXCLUDED.allow_na,
    tiers = EXCLUDED.tiers, display_order = EXCLUDED.display_order;
INSERT INTO public.investigation_ai_checklist_checkpoint (section, checkpoint_id, sub_criteria, checkpoint_text, max_marks, kind, allow_na, tiers, display_order) VALUES
    ('rc', '1', '1 Root Cause / Probable Causes', 'Classify the root-cause conclusion: ''assignable'' = proven through evidence, reproducible, direct linkage established (30); ''probable'' = evidence/data suggest a likely reason, scientifically justified (20); ''none'' = no root cause established (-5).', 30.0, 'classification', false, '{"assignable": 30.0, "probable": 20.0, "none": -5.0}'::jsonb, 1)
ON CONFLICT (section, checkpoint_id) DO UPDATE SET
    sub_criteria = EXCLUDED.sub_criteria, checkpoint_text = EXCLUDED.checkpoint_text,
    max_marks = EXCLUDED.max_marks, kind = EXCLUDED.kind, allow_na = EXCLUDED.allow_na,
    tiers = EXCLUDED.tiers, display_order = EXCLUDED.display_order;
INSERT INTO public.investigation_ai_checklist_checkpoint (section, checkpoint_id, sub_criteria, checkpoint_text, max_marks, kind, allow_na, tiers, display_order) VALUES
    ('impact', '6.1a', '6.1 Final Impact Assessment on Current Batches', 'Impact on the current/affected batch(es) is accurately identified (patient safety, product quality, area compliance status or other status such as documentation) based on the nature of the non-conformance.', 2.0, 'binary', true, NULL, 1)
ON CONFLICT (section, checkpoint_id) DO UPDATE SET
    sub_criteria = EXCLUDED.sub_criteria, checkpoint_text = EXCLUDED.checkpoint_text,
    max_marks = EXCLUDED.max_marks, kind = EXCLUDED.kind, allow_na = EXCLUDED.allow_na,
    tiers = EXCLUDED.tiers, display_order = EXCLUDED.display_order;
INSERT INTO public.investigation_ai_checklist_checkpoint (section, checkpoint_id, sub_criteria, checkpoint_text, max_marks, kind, allow_na, tiers, display_order) VALUES
    ('impact', '6.1c', '6.1 Final Impact Assessment on Current Batches', 'Where product quality / patient safety is impacted, the requirement of regulatory submission / market notification has been evaluated — or it is appropriately reasoned that none is required.', 1.0, 'binary', true, NULL, 2)
ON CONFLICT (section, checkpoint_id) DO UPDATE SET
    sub_criteria = EXCLUDED.sub_criteria, checkpoint_text = EXCLUDED.checkpoint_text,
    max_marks = EXCLUDED.max_marks, kind = EXCLUDED.kind, allow_na = EXCLUDED.allow_na,
    tiers = EXCLUDED.tiers, display_order = EXCLUDED.display_order;
INSERT INTO public.investigation_ai_checklist_checkpoint (section, checkpoint_id, sub_criteria, checkpoint_text, max_marks, kind, allow_na, tiers, display_order) VALUES
    ('impact', '6.1d', '6.1 Final Impact Assessment on Current Batches', 'Where product quality or regulatory compliance is impacted, continuation of production in similar areas/sites has been evaluated — or it is appropriately reasoned as not applicable.', 1.0, 'binary', true, NULL, 3)
ON CONFLICT (section, checkpoint_id) DO UPDATE SET
    sub_criteria = EXCLUDED.sub_criteria, checkpoint_text = EXCLUDED.checkpoint_text,
    max_marks = EXCLUDED.max_marks, kind = EXCLUDED.kind, allow_na = EXCLUDED.allow_na,
    tiers = EXCLUDED.tiers, display_order = EXCLUDED.display_order;
INSERT INTO public.investigation_ai_checklist_checkpoint (section, checkpoint_id, sub_criteria, checkpoint_text, max_marks, kind, allow_na, tiers, display_order) VALUES
    ('impact', '6.2a', '6.2 Extended Impact Assessment', 'Impact on other batches / area / process / products / systems has been mentioned with rationale (patient safety, product quality, compliance, documentation) — or, if there is no impact on other product, that has been stated.', 2.0, 'binary', false, NULL, 4)
ON CONFLICT (section, checkpoint_id) DO UPDATE SET
    sub_criteria = EXCLUDED.sub_criteria, checkpoint_text = EXCLUDED.checkpoint_text,
    max_marks = EXCLUDED.max_marks, kind = EXCLUDED.kind, allow_na = EXCLUDED.allow_na,
    tiers = EXCLUDED.tiers, display_order = EXCLUDED.display_order;
INSERT INTO public.investigation_ai_checklist_checkpoint (section, checkpoint_id, sub_criteria, checkpoint_text, max_marks, kind, allow_na, tiers, display_order) VALUES
    ('impact', '6.2b', '6.2 Extended Impact Assessment', 'If only the current batch/area/process is impacted and there is no impact on other batches, the rationale for the same has been mentioned.', 2.0, 'binary', false, NULL, 5)
ON CONFLICT (section, checkpoint_id) DO UPDATE SET
    sub_criteria = EXCLUDED.sub_criteria, checkpoint_text = EXCLUDED.checkpoint_text,
    max_marks = EXCLUDED.max_marks, kind = EXCLUDED.kind, allow_na = EXCLUDED.allow_na,
    tiers = EXCLUDED.tiers, display_order = EXCLUDED.display_order;
INSERT INTO public.investigation_ai_checklist_checkpoint (section, checkpoint_id, sub_criteria, checkpoint_text, max_marks, kind, allow_na, tiers, display_order) VALUES
    ('impact', '6.3', '6.3 Batch Disposition', 'The batch disposition decision is clearly written, if applicable (i.e. whether the non-conformance affects release of the current / other batches).', 2.0, 'binary', true, NULL, 6)
ON CONFLICT (section, checkpoint_id) DO UPDATE SET
    sub_criteria = EXCLUDED.sub_criteria, checkpoint_text = EXCLUDED.checkpoint_text,
    max_marks = EXCLUDED.max_marks, kind = EXCLUDED.kind, allow_na = EXCLUDED.allow_na,
    tiers = EXCLUDED.tiers, display_order = EXCLUDED.display_order;
INSERT INTO public.investigation_ai_checklist_checkpoint (section, checkpoint_id, sub_criteria, checkpoint_text, max_marks, kind, allow_na, tiers, display_order) VALUES
    ('capa', '7.1a', '7.1 Remedial Action (Correction)', 'The correction addresses the non-conformance (if applicable).', 1.0, 'binary', true, NULL, 1)
ON CONFLICT (section, checkpoint_id) DO UPDATE SET
    sub_criteria = EXCLUDED.sub_criteria, checkpoint_text = EXCLUDED.checkpoint_text,
    max_marks = EXCLUDED.max_marks, kind = EXCLUDED.kind, allow_na = EXCLUDED.allow_na,
    tiers = EXCLUDED.tiers, display_order = EXCLUDED.display_order;
INSERT INTO public.investigation_ai_checklist_checkpoint (section, checkpoint_id, sub_criteria, checkpoint_text, max_marks, kind, allow_na, tiers, display_order) VALUES
    ('capa', '7.1b', '7.1 Remedial Action (Correction)', 'Evidence / justification is provided for the correction done (if applicable).', 1.0, 'binary', true, NULL, 2)
ON CONFLICT (section, checkpoint_id) DO UPDATE SET
    sub_criteria = EXCLUDED.sub_criteria, checkpoint_text = EXCLUDED.checkpoint_text,
    max_marks = EXCLUDED.max_marks, kind = EXCLUDED.kind, allow_na = EXCLUDED.allow_na,
    tiers = EXCLUDED.tiers, display_order = EXCLUDED.display_order;
INSERT INTO public.investigation_ai_checklist_checkpoint (section, checkpoint_id, sub_criteria, checkpoint_text, max_marks, kind, allow_na, tiers, display_order) VALUES
    ('capa', '7.2', '7.2 Corrective Action / Preventive Action (CAPA)', 'The CAPA is consistent with the problem statement and investigation findings, contradicting nothing established during the investigation.', 10.0, 'binary', true, NULL, 3)
ON CONFLICT (section, checkpoint_id) DO UPDATE SET
    sub_criteria = EXCLUDED.sub_criteria, checkpoint_text = EXCLUDED.checkpoint_text,
    max_marks = EXCLUDED.max_marks, kind = EXCLUDED.kind, allow_na = EXCLUDED.allow_na,
    tiers = EXCLUDED.tiers, display_order = EXCLUDED.display_order;
INSERT INTO public.investigation_ai_checklist_checkpoint (section, checkpoint_id, sub_criteria, checkpoint_text, max_marks, kind, allow_na, tiers, display_order) VALUES
    ('capa', '7.3', '7.2 Corrective Action / Preventive Action (CAPA)', 'Interim control is explained appropriately with clear objectives, responsibilities and a timeline (or appropriate justification if not applicable).', 4.0, 'binary', true, NULL, 4)
ON CONFLICT (section, checkpoint_id) DO UPDATE SET
    sub_criteria = EXCLUDED.sub_criteria, checkpoint_text = EXCLUDED.checkpoint_text,
    max_marks = EXCLUDED.max_marks, kind = EXCLUDED.kind, allow_na = EXCLUDED.allow_na,
    tiers = EXCLUDED.tiers, display_order = EXCLUDED.display_order;
INSERT INTO public.investigation_ai_checklist_checkpoint (section, checkpoint_id, sub_criteria, checkpoint_text, max_marks, kind, allow_na, tiers, display_order) VALUES
    ('capa', '7.4', '7.2 Corrective Action / Preventive Action (CAPA)', 'CAPA scope is extended to other products / area / equipment as applicable (or appropriate justification if not applicable).', 4.0, 'binary', true, NULL, 5)
ON CONFLICT (section, checkpoint_id) DO UPDATE SET
    sub_criteria = EXCLUDED.sub_criteria, checkpoint_text = EXCLUDED.checkpoint_text,
    max_marks = EXCLUDED.max_marks, kind = EXCLUDED.kind, allow_na = EXCLUDED.allow_na,
    tiers = EXCLUDED.tiers, display_order = EXCLUDED.display_order;
