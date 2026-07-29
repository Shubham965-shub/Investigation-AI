-- Investigation AI — STAR schema.
--
-- Lives in the SAME shared Postgres instance as InvestigationAi_DS and this
-- backend's auth tables (see schema.sql) — NOT a separate database.
--
-- [AUTHORITATIVE] This file mirrors star_schema_new.sql, provided directly by
-- the data engineer building the real tables on the live Azure Postgres
-- instance (qa-lighthouse-db) — that DB is the source of truth, this file is
-- kept in sync with it, not the other way around. Comments below are ported
-- over from the earlier draft/validation pass for continuity; the engineer's
-- file itself has none. Every table/column below was re-verified directly
-- against the live DB (read-only) on 2026-07-24, not just against the raw
-- script file — the two are consistent except where noted.
--
-- DO NOT RUN THIS AGAINST ANY DATABASE WITHOUT EXPLICIT APPROVAL — the user
-- verifies this with the DB owner first.
--
-- Column annotations:
--   [BUG]       — a Gold-layer bug fix is encoded in this column/table
--   [DEAD]      — confirmed 0/44,018 populated; kept for future workflow stages
--   [DUPLICATE] — exact duplicate of another column; kept until downstream
--                 consumers are confirmed clear to drop it
--   [CORRECTED] — a type, fill-rate, or "confirmed dead/dropped" claim in an
--                 earlier version of the schema doc (or of this file) was
--                 validated as wrong against a fresh check
--   [ALIGNED]   — moved/renamed to match a real, already-existing table
--   [DROPPED]   — confirmed absent from the real schema entirely (not
--                 renamed/relocated — verified by column-name search across
--                 all tables and, where checked, by content search within
--                 matching rows). Per the data engineer: treat as
--                 intentionally unnecessary — this may include columns that
--                 are missing on purpose, not just oversights (2026-07-24).
--
-- 2026-07-24 update — DIM_INVESTIGATOR and DIM_RCI landed; DIM_ACTIVITY was
-- CANCELLED by the backend engineer (via user) — it will never be built.
-- Instead, the latest status for any event now lives directly on dim_event
-- (status/status_start_date/status_end_date columns, replacing the old
-- activity_type/status_origin/status_after trio that used to live there).

-- ── Dimension tables ─────────────────────────────────────────────────────

-- Real BI date-filter view — not part of the original design, found directly
-- on the live DB.
CREATE OR REPLACE VIEW public.dim_date AS
SELECT
    d::date AS date_key,
    EXTRACT(DAY FROM d)::INT AS day,
    EXTRACT(MONTH FROM d)::INT AS month,
    TO_CHAR(d, 'FMMonth') AS month_name,
    EXTRACT(YEAR FROM d)::INT AS year,
    TO_CHAR(d, 'FMMonth YYYY') AS month_year,
    CASE
        WHEN d >= CURRENT_DATE - INTERVAL '3 months' THEN 'Yes'
        ELSE 'No'
    END AS is_last_3_months,
    CASE
        WHEN d >= CURRENT_DATE - INTERVAL '6 months' THEN 'Yes'
        ELSE 'No'
    END AS is_last_6_months,
    CASE
        WHEN d >= CURRENT_DATE - INTERVAL '12 months' THEN 'Yes'
        ELSE 'No'
    END AS is_last_12_months
FROM generate_series(
        make_date(EXTRACT(YEAR FROM CURRENT_DATE)::INT - 9, 1, 1),
        CURRENT_DATE,
        INTERVAL '1 day'
     ) AS d;

-- [CORRECTED 2026-07-24] key is a plain INTEGER with no default (app/ETL
-- assigns it via ROW_NUMBER(), not a Postgres SERIAL sequence) — this file
-- previously called it SERIAL; confirmed wrong via live information_schema
-- check (column_default IS NULL). Same externally-assigned-key pattern as
-- dim_location/dim_department/dim_batch below, not a special case anymore.
CREATE TABLE IF NOT EXISTS public.dim_event_classification (
    event_classification_key INT PRIMARY KEY,
    qe_type TEXT                        -- Deviation/OOS/OOT/Complaint — 100% (live DB has this as VARCHAR, not TEXT — cosmetic, functionally identical)
);

-- [ALIGNED] slimmed to match the real DB — all other columns moved to
-- dim_event. Confirmed canonical by the data engineer (2026-07-23) —
-- dim_name_of_material (an exact duplicate that briefly existed) will be
-- dropped, not this table.
-- [CORRECTED 2026-07-24] key is plain INTEGER, not SERIAL — same correction
-- as dim_event_classification above.
CREATE TABLE IF NOT EXISTS public.dim_product (
    product_key INT PRIMARY KEY,
    name_of_material TEXT                                            -- 97% across all types — [BUG] reaches 742 chars in source data against this column's 255-char limit (14/44,018 rows); engineer will address
);

-- location_key is a plain INT (not SERIAL) here — the ETL assigns this key,
-- not Postgres.
CREATE TABLE IF NOT EXISTS public.dim_location (
    location_key INT PRIMARY KEY,
    location TEXT NOT NULL               -- 100% all types
);

-- [ALIGNED] slimmed to match the real DB — equipment_number/laboratory_details/
-- name_of_test/sample_number/specification_number moved to dim_event.
-- [CORRECTED 2026-07-24] key is plain INTEGER, not SERIAL — same correction
-- as dim_event_classification/dim_product above.
CREATE TABLE IF NOT EXISTS public.dim_equipment (
    equipment_key INT PRIMARY KEY,
    instrument_equipment TEXT,      -- equipment name — [BUG] distinct from instrument_equipment_id, not a duplicate
    instrument_equipment_id TEXT    -- equipment ID — [BUG] distinct from instrument_equipment, not a duplicate
);

-- Same externally-assigned-key pattern as dim_location.
CREATE TABLE IF NOT EXISTS public.dim_department (
    department_key INT PRIMARY KEY,
    department TEXT NOT NULL
);

-- batch_no split out of dim_event/dim_product into its own table. Same
-- externally-assigned-key pattern as dim_location/dim_department.
CREATE TABLE IF NOT EXISTS public.dim_batch (
    batch_key INT PRIMARY KEY,
    batch_no TEXT NOT NULL          -- COALESCE(batch_number_ar_number, batch_number) — 97%
);

-- NEW (2026-07-24). One row per Trackwise "assignee" — a single free-text
-- name, NOT a consolidation of dim_event's own originator/analyst_name/
-- owner_name/observed_by columns (those all stay put on dim_event, untouched
-- — see below). fact_qms_event.investigator_key FKs here via source column
-- assignee_id. This is the real, queryable "who is this case assigned to"
-- link — relevant to the still-unimplemented investigator auto-assignment
-- rule (see project memory: investigator_auto_assignment) once combined with
-- dim_event.status for an open-case count per investigator.
CREATE TABLE IF NOT EXISTS public.dim_investigator (
    investigator_key INT PRIMARY KEY,
    investigator TEXT NOT NULL
);

-- NEW (2026-07-24). Pulls root_cause_summary/root_cause_conclusion OFF
-- dim_event into their own dimension, keyed by the source's rci_id
-- (aliased rci_key here). [CORRECTED] rci_id was previously listed as one
-- of 13 confirmed-dropped source columns in this project's schema notes —
-- that was wrong; it was never dropped, just promoted into this new table.
-- reference_number is a genuinely new column, not seen in the sample data
-- validated so far.
CREATE TABLE IF NOT EXISTS public.dim_rci (
    rci_key INT PRIMARY KEY,
    reference_number TEXT,
    root_cause_summary TEXT,        -- moved off dim_event — blank/open items store '' not NULL
    root_cause_conclusion TEXT      -- moved off dim_event — [DUPLICATE] of root_cause_summary per earlier validation; re-check once this table has real data
);

-- dim_stability, dim_capa, dim_complaint removed — [ALIGNED] their columns
-- live on dim_event instead.

-- One row per event (deviation_id = PK), denormalised narrative/investigation
-- text. Absorbs everything moved off dim_event_classification/dim_location/
-- dim_equipment/dim_product plus all of dim_stability/dim_capa/dim_complaint
-- — [ALIGNED]. date_opened/date_closed/due_date/closed_on and batch_no moved
-- to fact_qms_event/dim_batch respectively — commented out below rather than
-- omitted, to keep that move visible.
--
-- 2026-07-24: significantly expanded (85 → 107 columns) and re-verified
-- live. Notable changes from the previous version of this file:
--   - root_cause_summary/root_cause_conclusion MOVED to new dim_rci table.
--   - activity_type/status_origin/status_after REPLACED by status/
--     status_start_date/status_end_date (DIM_ACTIVITY was cancelled — see
--     header note and project memory: module_progress_grouping).
--   - equipment_number [DROPPED] — no replacement; Deviation-extended's
--     "Equipment ID" frontend field has no source anymore (field_mapping.py
--     hardcodes None, same pattern as "Products Information").
--   - capa_implementation_date_e_signature_and_qa_closure_on [DEAD] column
--     is gone, replaced by two real separate columns: e_signature_certificate
--     and qa_closure_on.
--   - deviation_owner is now a REAL column — [CORRECTED] this file previously
--     said owner_name = COALESCE(deviation_owner, qc_manager) "at source;
--     deviation_owner doesn't exist as a real source column" — that claim
--     was wrong; deviation_owner is live and distinct from owner_name/
--     qc_manager below.
--   - qc_manager is now its own real column (previously only inferred via
--     owner_name's COALESCE).
--   - immediate_actions_and_assessment, corrective_actions_and_preventive_
--     actions, correction_corrective_and_preventive_actions (the latter two
--     were a [DUPLICATE] pair), investigation_tasks, and
--     immediate_containment_actions are all GONE — not present in the live
--     107-column set. Not yet confirmed whether genuinely dropped or
--     relocated; flag with the data engineer if any downstream code needs
--     them (none currently does).
--   - New, previously-unseen columns: affected_batches_batch_ar_number[]/
--     affected_batches_product_material_name[] and batches_details_batch_
--     no_ar_no[]/batches_details_product_or_material_name[] — two candidate
--     array pairs that may resolve the long-standing "OOS/OOT Batches
--     Details has no clear source column" gap in field_mapping.py, but which
--     (if either) maps to that frontend field is unconfirmed — not wired up
--     yet. Also new: complaint_related_to, counterfeiting_details,
--     doc_updated_for_above_actions, e_signature_certificate,
--     explain_if_not_injected, explain_the_reason, explanation_1-4,
--     explanation_reg_notification, health_hazard_evaluation,
--     impact_justification, impact_on_other_batches, investigation_results,
--     material_is_quarantined, medical_impact_analysis,
--     medical_investigation_summary, nature_of_complaint, primary_defect,
--     qa_closure_on, rationale_for_recall_decision, re_dilution_results,
--     re_injection_results, reserve_sample_observations,
--     segregation_of_the_material, stability_review_comments, sub_area,
--     supporting_documents, suspension_of_the_operation — none of these are
--     wired into field_mapping.py yet; surfacing them here for visibility,
--     not implying they're all relevant to the current 4 frontend modules.
CREATE TABLE IF NOT EXISTS public.dim_event (
    deviation_id INTEGER PRIMARY KEY,
    title TEXT,
    description TEXT,
    -- [DROPPED] description_of_event — 100% filled in source (structured JSON
    -- 6-question investigation template); confirmed absent from this table
    -- entirely, not renamed/relocated elsewhere.
    --date_opened TIMESTAMP,                                   -- moved to fact_qms_event
    --date_closed TIMESTAMP,                                   -- moved to fact_qms_event
    --due_date TIMESTAMP,                                       -- moved to fact_qms_event
    --closed_on TIMESTAMP,                                      -- moved to fact_qms_event
    observation_date DATE,
    observation_time TEXT,
    failure_duration TEXT,                                    -- Deviation only
    repeated_deviation TEXT,                                   -- Deviation only
    immediate_cause_known TEXT,                                -- Deviation only
    cause_detail TEXT,                                         -- Deviation only
    root_cause_sub_category TEXT,
    root_cause_category TEXT,                                  -- [DEAD]
    investigation_summary TEXT,                                -- Deviation only
    immediate_actions TEXT,                                    -- Deviation only
    impact_analysis TEXT,                                      -- Deviation only
    impact_details TEXT,                                       -- Deviation only
    impact_on_deviation_batches TEXT,                          -- Deviation only
    impact_on_other_batches TEXT,                              -- new 2026-07-24
    actions_taken TEXT,                                        -- [DEAD]
    actions_to_be_completed TEXT,
    actions_to_be_completed_not_use TEXT,                      -- Deviation only
    correction_or_remedial_action TEXT,                        -- Deviation only
    proposal_for_resolution TEXT,                              -- Deviation only
    -- [GONE 2026-07-24, not yet confirmed dropped vs. relocated]
    -- immediate_actions_and_assessment, corrective_actions_and_preventive_
    -- actions, correction_corrective_and_preventive_actions (was
    -- [DUPLICATE] of the former), investigation_tasks,
    -- immediate_containment_actions — see table-level comment above.
    status TEXT,                                               -- new 2026-07-24, replaces activity_type/status_origin/status_after (DIM_ACTIVITY cancelled)
    status_start_date TIMESTAMP,                               -- new 2026-07-24
    status_end_date TIMESTAMP,                                 -- new 2026-07-24
    workflow_status TEXT,                                      -- [DEAD]
    deviation_number TEXT,                                     -- Deviation only
    deviation_to TEXT,                                         -- Deviation only
    report_delay_justification TEXT,                           -- Deviation only
    em_failure_checklist_response TEXT[],                      -- rare (38/44,018 non-empty) but not all 'Not Applicable' — 16 of those 38 hold real Yes/No answers across a 22-23 item EM checklist
    risk_analysis TEXT,                                        -- [DEAD]
    number_of_times_events_occurred TEXT,                      -- [DEAD]
    other TEXT,                                                -- [DEAD]
    notification_sent_to_customer_mah_on TEXT,                 -- Deviation only
    -- [DROPPED] impact_assessment_and_conclusion_batch_disposition — 100%
    -- filled in source (structured JSON); confirmed absent entirely.
    originator TEXT,                                           -- creator in Trackwise — 100% — stays on dim_event; NOT consolidated into dim_investigator (that table is a distinct "assignee" concept, see above)
    analyst_name TEXT,                                         -- OOS/OOT only — stays on dim_event
    owner_name TEXT,                                           -- COALESCE(deviation_owner, qc_manager) at source — stays on dim_event; deviation_owner and qc_manager below are now also real, separate columns
    deviation_owner TEXT,                                      -- [CORRECTED 2026-07-24] real column — see table-level comment above
    qc_manager TEXT,                                           -- new 2026-07-24 — see table-level comment above
    observed_by TEXT,                                          -- Deviation only — 98% — stays on dim_event
    category TEXT,                                             -- Deviation only — 75%
    broad_category TEXT,                                       -- Deviation only — 75%
    final_categorization TEXT,                                 -- Deviation only — 74%
    failure_type TEXT,                                          -- OOS only — 95%
    market TEXT,                                               -- Complaint only — same concept as related_market, split by event type
    related_market TEXT[],                                     -- Dev/OOS/OOT only — same concept as market, split by event type
    -- [DROPPED 2026-07-24] equipment_number — Deviation only, was 99% —
    -- confirmed absent from the live 107-column dim_event; no replacement.
    -- field_mapping.py's Deviation-extended "Equipment ID" is now always
    -- None (was previously sourced from this column).
    laboratory_details TEXT,                                   -- OOS/OOT only
    name_of_test TEXT,                                         -- OOS/OOT
    sample_number TEXT,                                        -- OOS/OOT
    specification_number TEXT,                                 -- OOS/OOT
    stability_condition TEXT,                                  -- OOS/OOT — correctly 0% for Complaint/Dev
    stability_protocol_number TEXT,                            -- OOS/OOT
    stability_review_comments TEXT,                            -- new 2026-07-24
    stability_time_point TEXT,                                 -- OOS/OOT
    stp_number TEXT,                                           -- OOS/OOT
    labelled_storage_conditions TEXT,                          -- OOS/OOT
    capa_record_id TEXT,                                       -- [CORRECTED] confirmed plain comma-separated text (e.g. '1083, 1090'), permanently — not an array, per engineer (2026-07-23)
    capa_number TEXT[],                                        -- 22% overall
    capa_implementation_date TEXT,                             -- Deviation only — 91%
    capa_effectiveness TEXT,                                   -- [DEAD]
    capa_details TEXT,                                         -- [DEAD]
    -- [GONE 2026-07-24] capa_implementation_date_e_signature_and_qa_closure_on
    -- (previously [DEAD]) — replaced by two real separate columns:
    -- e_signature_certificate and qa_closure_on below.
    e_signature_certificate TEXT,                              -- new 2026-07-24
    qa_closure_on TEXT,                                        -- new 2026-07-24
    complaint_number TEXT,                                     -- Complaint only — 97%
    complaint_related_to TEXT,                                 -- new 2026-07-24
    complainant_name TEXT,                                     -- Complaint only — 97%
    complainant_country TEXT,                                  -- Complaint only — 97%
    complaint_received_by TEXT,                                -- Complaint only — 97%
    complaint_reported_by TEXT,                                -- Complaint only — 70%
    customer TEXT,                                             -- Complaint only — 100%
    date_complaint_received DATE,                              -- Complaint only — 100%
    reference_complaint_number TEXT,                           -- Complaint only — 26%
    nature_of_complaint TEXT,                                  -- new 2026-07-24
    counterfeiting_details TEXT,                               -- new 2026-07-24
    sfg_code TEXT,                                             -- Dev/OOS/OOT 99% · 0% Complaint
    product_type TEXT,                                         -- OOS/OOT only
    dosage_form TEXT,                                          -- Complaint only — 97%
    product_manufacturing_info TEXT,                           -- Complaint only — 97%
    --batch_no TEXT,                                            -- moved to dim_batch
    related_customer TEXT[],                                   -- [BUG] moved from DIM_COMPLAINT, then from dim_product — Dev/OOS/OOT ~99% · 0% Complaint
    affected_batches_batch_ar_number TEXT[],                    -- new 2026-07-24 — see table-level comment above (candidate "Batches Details" source)
    affected_batches_product_material_name TEXT[],              -- new 2026-07-24
    batches_details_batch_no_ar_no TEXT[],                      -- new 2026-07-24 — see table-level comment above (candidate "Batches Details" source)
    batches_details_product_or_material_name TEXT[],            -- new 2026-07-24
    qty_of_material_quarantined TEXT,                          -- [CORRECTED 2026-07-24] previously listed as one of 13 confirmed-dropped source columns — that was wrong; it's live here (35.5% filled per earlier sample check)
    material_is_quarantined TEXT,                              -- new 2026-07-24
    segregation_of_the_material TEXT,                          -- new 2026-07-24
    rationale_for_recall_decision TEXT,                        -- new 2026-07-24
    re_dilution_results TEXT,                                  -- new 2026-07-24
    re_injection_results TEXT,                                 -- new 2026-07-24
    reserve_sample_observations TEXT,                          -- new 2026-07-24
    health_hazard_evaluation TEXT,                             -- new 2026-07-24
    medical_impact_analysis TEXT,                              -- new 2026-07-24
    medical_investigation_summary TEXT,                        -- new 2026-07-24
    investigation_results TEXT,                                -- new 2026-07-24
    impact_justification TEXT,                                 -- new 2026-07-24
    primary_defect TEXT,                                       -- new 2026-07-24
    explain_if_not_injected TEXT,                               -- new 2026-07-24
    explain_the_reason TEXT,                                    -- new 2026-07-24
    explanation_1 TEXT,                                        -- new 2026-07-24
    explanation_2 TEXT,                                        -- new 2026-07-24
    explanation_3 TEXT,                                        -- new 2026-07-24
    explanation_4 TEXT,                                        -- new 2026-07-24
    explanation_reg_notification TEXT,                         -- new 2026-07-24
    doc_updated_for_above_actions TEXT,                         -- new 2026-07-24
    supporting_documents TEXT,                                 -- new 2026-07-24
    suspension_of_the_operation TEXT,                          -- new 2026-07-24
    sub_area TEXT                                              -- new 2026-07-24
    -- [DROPPED] products_information_product_name — Complaint only, 13.1%
    -- overall (~100% within Complaint); confirmed absent entirely.
    -- [DROPPED] date_updated — confirmed absent entirely (still, as of
    -- 2026-07-24 re-check).
    -- [DROPPED] the whole initial_impact_assessment_* group (7 columns,
    -- 49-97% filled each) — confirmed absent entirely (still, as of
    -- 2026-07-24 re-check).
);

-- ── Fact table ───────────────────────────────────────────────────────────
-- Grain: one row per QMS event (Deviation, OOS, OOT, Market Complaint).
--
-- composite_primary_key is the real PK — NOT deviation_id. Per the data
-- engineer (2026-07-23): a new composite key derived from deviation_id plus
-- a few other columns, created because deviation_id alone is no longer
-- unique here (274 deviation_ids have more than one row in the live table).
--
-- [DROPPED] unique_id, date_updated — confirmed absent from this table
-- entirely (not renamed/relocated). rci_id and qty_of_material_quarantined
-- were previously listed here too — [CORRECTED 2026-07-24]: rci_id now
-- lives as fact_qms_event.rci_key (FK to the new dim_rci table, see below —
-- ALIGNED, not dropped) and qty_of_material_quarantined lives on dim_event
-- (also not dropped, just never on this fact table specifically).
--
-- 2026-07-24: FK set is now 9 constraints (was 7, explicitly flagged
-- [PROVISIONAL] pending DIM_INVESTIGATOR/DIM_ACTIVITY). DIM_ACTIVITY was
-- cancelled, but DIM_INVESTIGATOR landed and DIM_RCI appeared as well — both
-- now have live FKs below. Re-verified directly against the DB (all 9 exist).
-- Likely the final set, but treat as provisional until the engineer
-- explicitly confirms no more dimensions are coming.
CREATE TABLE IF NOT EXISTS public.fact_qms_event (
    composite_primary_key TEXT PRIMARY KEY,

    date_opened TIMESTAMP,
    date_closed TIMESTAMP,                 -- OOS/OOT closed-date column — see time_elapsed [BUG]
    due_date TIMESTAMP,
    closed_on TIMESTAMP,                   -- Complaint/Dev closed-date column — see time_elapsed [BUG]

    location_key INTEGER,
    event_classification_key INTEGER,
    equipment_key INTEGER,
    department_key INTEGER,
    product_key INTEGER,
    deviation_id INTEGER,                  -- no longer unique/PK — see header note
    batch_key INTEGER,
    investigator_key INTEGER,              -- new 2026-07-24 — FK to dim_investigator (source: assignee_id)
    rci_key INTEGER,                       -- new 2026-07-24 — FK to dim_rci (source: rci_id)

    time_elapsed INTEGER,                  -- [BUG] fixed as DATEDIFF(COALESCE(closed_on, date_closed), date_opened) in the Gold-layer transform that populates this column
    pg_updated_at_timestamp TIMESTAMP,     -- renamed from lk_updated_at_timestamp in the data dictionary

    CONSTRAINT fk_fact_location
        FOREIGN KEY (location_key)
        REFERENCES public.dim_location(location_key),

    CONSTRAINT fk_fact_event_classification
        FOREIGN KEY (event_classification_key)
        REFERENCES public.dim_event_classification(event_classification_key),

    CONSTRAINT fk_fact_equipment
        FOREIGN KEY (equipment_key)
        REFERENCES public.dim_equipment(equipment_key),

    CONSTRAINT fk_fact_department
        FOREIGN KEY (department_key)
        REFERENCES public.dim_department(department_key),

    CONSTRAINT fk_fact_product
        FOREIGN KEY (product_key)
        REFERENCES public.dim_product(product_key),

    CONSTRAINT fk_fact_event
        FOREIGN KEY (deviation_id)
        REFERENCES public.dim_event(deviation_id),

    CONSTRAINT fk_fact_batch
        FOREIGN KEY (batch_key)
        REFERENCES public.dim_batch(batch_key),

    CONSTRAINT fk_fact_investigator
        FOREIGN KEY (investigator_key)
        REFERENCES public.dim_investigator(investigator_key),

    CONSTRAINT fk_fact_rci
        FOREIGN KEY (rci_key)
        REFERENCES public.dim_rci(rci_key)
);
