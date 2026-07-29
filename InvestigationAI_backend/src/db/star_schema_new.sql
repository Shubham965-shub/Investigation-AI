-- DIM_INVESTIGATOR
CREATE TABLE IF NOT EXISTS public.dim_investigator (
    investigator_key INT PRIMARY KEY,
    investigator TEXT NOT NULL
);

SELECT DISTINCT
    assignee_id AS investigator_key,
    TRIM(assignee) AS investigator
FROM public.investigation_ai_sample_test
WHERE assignee IS NOT NULL
  AND TRIM(assignee) <> '';

select * from public.dim_investigator;

-- DIM DATE
CREATE OR REPLACE VIEW public.dim_date AS

SELECT
    d::DATE AS date_key,
    EXTRACT(DAY FROM d)::INT AS day,
    EXTRACT(MONTH FROM d)::INT AS month,
    TO_CHAR(d, 'FMMonth') AS month_name,
    EXTRACT(YEAR FROM d)::INT AS year,
    TO_CHAR(d, 'FMMonth YYYY') AS month_year,

    CASE
        WHEN d>= CURRENT_DATE - INTERVAL '30 days' THEN 'Yes'
        ELSE 'No'
    END AS is_last_30_days,

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

select * from public.dim_date;

-- DIM_LOCATION
CREATE TABLE IF NOT EXISTS public.dim_location (
    location_key INT PRIMARY KEY,
    location TEXT NOT NULL
);

INSERT INTO public.dim_location (
    location_key,
    location
)
SELECT
    ROW_NUMBER() OVER (ORDER BY location) AS location_key,
    location
FROM (
    SELECT DISTINCT
        TRIM(location) AS location
    FROM public.investigation_ai_sample_test
    WHERE location IS NOT NULL
      AND TRIM(location) <> ''
) t;

-- DIM_EVENT_CLASSIFICATION
CREATE TABLE IF NOT EXISTS public.dim_event_classification (
    event_classification_key INT PRIMARY KEY,
    qe_type TEXT NOT NULL
);


SELECT
    ROW_NUMBER() OVER (ORDER BY qe_type) AS event_classification_key,
    qe_type
FROM (
    SELECT DISTINCT
        TRIM(qe_type) AS qe_type
    FROM public.investigation_ai_sample_test
    WHERE qe_type IS NOT NULL
      AND TRIM(qe_type) <> ''
) t;

SELECT *
FROM public.dim_event_classification;

-- DIM_EQUIPMENT
CREATE TABLE IF NOT EXISTS public.dim_equipment (
    equipment_key INT PRIMARY KEY,
    instrument_equipment TEXT,
    instrument_equipment_id TEXT

INSERT INTO public.dim_equipment (
    equipment_key,
    instrument_equipment,
    instrument_equipment_id
)
SELECT
    ROW_NUMBER() OVER (
        ORDER BY
            instrument_equipment,
            instrument_equipment_id
    ) AS equipment_key,
    instrument_equipment,
    instrument_equipment_id
FROM (
    SELECT DISTINCT
        TRIM(instrument_equipment) AS instrument_equipment,
        TRIM(instrument_equipment_id) AS instrument_equipment_id
    FROM public.investigation_ai_sample_test
    WHERE instrument_equipment IS NOT NULL
       OR instrument_equipment_id IS NOT NULL
) t;

SELECT *
FROM public.dim_equipment;

-- DIM_DEPARTMENT
CREATE TABLE IF NOT EXISTS public.dim_department (
    department_key INT PRIMARY KEY,
    department TEXT NOT NULL
);

INSERT INTO public.dim_department (
    department_key,
    department
)
SELECT
    ROW_NUMBER() OVER (ORDER BY department) AS department_key,
    department
FROM (
    SELECT DISTINCT
        TRIM(department) AS department
    FROM public.investigation_ai_sample_test
    WHERE department IS NOT NULL
      AND TRIM(department) <> ''
) t;

SELECT *
FROM public.dim_department;

-- DIM_PRODUCT
CREATE TABLE IF NOT EXISTS public.dim_product (
    product_key INT PRIMARY KEY,
    name_of_material TEXT NOT NULL
);

INSERT INTO public.dim_product (
    product_key,
    name_of_material
)
SELECT
    ROW_NUMBER() OVER (ORDER BY name_of_material) AS product_key,
    name_of_material
FROM (
    SELECT DISTINCT
        TRIM(name_of_material) AS name_of_material
    FROM public.investigation_ai_sample_test
    WHERE name_of_material IS NOT NULL
      AND TRIM(name_of_material) <> ''
) t;

SELECT COUNT(*)
FROM public.dim_product;

-- DIM_BATCH
CREATE TABLE IF NOT EXISTS public.dim_batch (
    batch_key INT PRIMARY KEY,
    batch_no TEXT NOT NULL
);

INSERT INTO public.dim_batch (
    batch_key,
    batch_no
)
SELECT
    ROW_NUMBER() OVER (ORDER BY batch_no) AS batch_key,
    batch_no
FROM (
    SELECT DISTINCT
        TRIM(batch_no) AS batch_no
    FROM public.investigation_ai_sample_test
    WHERE batch_no IS NOT NULL
      AND TRIM(batch_no) <> ''
) t;

SELECT COUNT(*)
FROM public.dim_batch;

-- DIM_EVENT

drop table public.dim_event;

cREATE TABLE IF NOT EXISTS public.dim_event (
    deviation_id INTEGER PRIMARY KEY,
    actions_taken TEXT,
    actions_to_be_completed TEXT,
    actions_to_be_completed_not_use TEXT,
    affected_batches_batch_ar_number TEXT[],
    affected_batches_product_material_name TEXT[],
    analyst_name TEXT,
    batches_details_batch_no_ar_no TEXT[],
    batches_details_product_or_material_name TEXT[],
    broad_category TEXT,
    capa_details TEXT,
    capa_effectiveness TEXT,
    capa_implementation_date TEXT,
    capa_number TEXT[],
    capa_record_id TEXT,
    category TEXT,
    cause_detail TEXT,
    complainant_country TEXT,
    complainant_name TEXT,
    complaint_number TEXT,
    complaint_received_by TEXT,
    complaint_related_to TEXT,
    complaint_reported_by TEXT,
    correction_or_remedial_action TEXT,
    counterfeiting_details TEXT,
    customer TEXT,
    date_complaint_received DATE,
    description TEXT,
    deviation_number TEXT,
    deviation_owner TEXT,
    deviation_to TEXT,
    doc_updated_for_above_actions TEXT,
    dosage_form TEXT,
    e_signature_certificate TEXT,
    em_failure_checklist_response TEXT[],
    explain_if_not_injected TEXT,
    explain_the_reason TEXT,
    explanation_1 TEXT,
    explanation_2 TEXT,
    explanation_3 TEXT,
    explanation_4 TEXT,
    explanation_reg_notification TEXT,
    failure_duration TEXT,
    failure_type TEXT,
    final_categorization TEXT,
    health_hazard_evaluation TEXT,
    immediate_actions TEXT,
    immediate_cause_known TEXT,
    impact_analysis TEXT,
    impact_details TEXT,
    impact_justification TEXT,
    impact_on_deviation_batches TEXT,
    impact_on_other_batches TEXT,
    investigation_results TEXT,
    investigation_summary TEXT,
    labelled_storage_conditions TEXT,
    laboratory_details TEXT,
    market TEXT,
    material_is_quarantined TEXT,
    medical_impact_analysis TEXT,
    medical_investigation_summary TEXT,
    name_of_test TEXT,
    nature_of_complaint TEXT,
    notification_sent_to_customer_mah_on TEXT,
    number_of_times_events_occurred TEXT,
    observation_date DATE,
    observation_time TEXT,
    observed_by TEXT,
    originator TEXT,
    other TEXT,
    owner_name TEXT,
    primary_defect TEXT,
    product_manufacturing_info TEXT,
    product_type TEXT,
    proposal_for_resolution TEXT,
    qa_closure_on TEXT,
    qc_manager TEXT,
    qty_of_material_quarantined TEXT,
    rationale_for_recall_decision TEXT,
    re_dilution_results TEXT,
    re_injection_results TEXT,
    reference_complaint_number TEXT,
    related_customer TEXT[],
    related_market TEXT[],
    repeated_deviation TEXT,
    report_delay_justification TEXT,
    reserve_sample_observations TEXT,
    risk_analysis TEXT,
    root_cause_category TEXT,
    root_cause_sub_category TEXT,
    sample_number TEXT,
    segregation_of_the_material TEXT,
    sfg_code TEXT,
    specification_number TEXT,
    stability_condition TEXT,
    stability_protocol_number TEXT,
    stability_review_comments TEXT,
    stability_time_point TEXT,
    status TEXT,
    status_end_date timestamp ,
    status_start_date timestamp,
    stp_number TEXT,
    sub_area TEXT,
    supporting_documents TEXT,
    suspension_of_the_operation TEXT,
    title TEXT,
    workflow_status TEXT
);

INSERT INTO public.dim_event (
    deviation_id,
    actions_taken,
    actions_to_be_completed,
    actions_to_be_completed_not_use,
    affected_batches_batch_ar_number,
    affected_batches_product_material_name,
    analyst_name,
    batches_details_batch_no_ar_no,
    batches_details_product_or_material_name,
    broad_category,
    capa_details,
    capa_effectiveness,
    capa_implementation_date,
    capa_number,
    capa_record_id,
    category,
    cause_detail,
    complainant_country,
    complainant_name,
    complaint_number,
    complaint_received_by,
    complaint_related_to,
    complaint_reported_by,
    correction_or_remedial_action,
    counterfeiting_details,
    customer,
    date_complaint_received,
    description,
    deviation_number,
    deviation_owner,
    deviation_to,
    doc_updated_for_above_actions,
    dosage_form,
    e_signature_certificate,
    em_failure_checklist_response,
    explain_if_not_injected,
    explain_the_reason,
    explanation_1,
    explanation_2,
    explanation_3,
    explanation_4,
    explanation_reg_notification,
    failure_duration,
    failure_type,
    final_categorization,
    health_hazard_evaluation,
    immediate_actions,
    immediate_cause_known,
    impact_analysis,
    impact_details,
    impact_justification,
    impact_on_deviation_batches,
    impact_on_other_batches,
    investigation_results,
    investigation_summary,
    labelled_storage_conditions,
    laboratory_details,
    market,
    material_is_quarantined,
    medical_impact_analysis,
    medical_investigation_summary,
    name_of_test,
    nature_of_complaint,
    notification_sent_to_customer_mah_on,
    number_of_times_events_occurred,
    observation_date,
    observation_time,
    observed_by,
    originator,
    other,
    owner_name,
    primary_defect,
    product_manufacturing_info,
    product_type,
    proposal_for_resolution,
    qa_closure_on,
    qc_manager,
    qty_of_material_quarantined,
    rationale_for_recall_decision,
    re_dilution_results,
    re_injection_results,
    reference_complaint_number,
    related_customer,
    related_market,
    repeated_deviation,
    report_delay_justification,
    reserve_sample_observations,
    risk_analysis,
    root_cause_category,
    root_cause_sub_category,
    sample_number,
    segregation_of_the_material,
    sfg_code,
    specification_number,
    stability_condition,
    stability_protocol_number,
    stability_review_comments,
    stability_time_point,
    status,
    status_end_date,
    status_start_date,
    stp_number,
    sub_area,
    supporting_documents,
    suspension_of_the_operation,
    title,
    workflow_status
)
SELECT DISTINCT
    deviation_id,
    actions_taken,
    actions_to_be_completed,
    actions_to_be_completed_not_use,
    affected_batches_batch_ar_number,
    affected_batches_product_material_name,
    analyst_name,
    batches_details_batch_no_ar_no,
    batches_details_product_or_material_name,
    broad_category,
    capa_details,
    capa_effectiveness,
    capa_implementation_date,
    capa_number,
    capa_record_id,
    category,
    cause_detail,
    complainant_country,
    complainant_name,
    complaint_number,
    complaint_received_by,
    complaint_related_to,
    complaint_reported_by,
    correction_or_remedial_action,
    counterfeiting_details,
    customer,
    date_complaint_received,
    description,
    deviation_number,
    deviation_owner,
    deviation_to,
    doc_updated_for_above_actions,
    dosage_form,
    e_signature_certificate,
    em_failure_checklist_response,
    explain_if_not_injected,
    explain_the_reason,
    explanation_1,
    explanation_2,
    explanation_3,
    explanation_4,
    explanation_reg_notification,
    failure_duration,
    failure_type,
    final_categorization,
    health_hazard_evaluation,
    immediate_actions,
    immediate_cause_known,
    impact_analysis,
    impact_details,
    impact_justification,
    impact_on_deviation_batches,
    impact_on_other_batches,
    investigation_results,
    investigation_summary,
    labelled_storage_conditions,
    laboratory_details,
    market,
    material_is_quarantined,
    medical_impact_analysis,
    medical_investigation_summary,
    name_of_test,
    nature_of_complaint,
    notification_sent_to_customer_mah_on,
    number_of_times_events_occurred,
    observation_date,
    observation_time,
    observed_by,
    originator,
    other,
    owner_name,
    primary_defect,
    product_manufacturing_info,
    product_type,
    proposal_for_resolution,
    qa_closure_on,
    qc_manager,
    qty_of_material_quarantined,
    rationale_for_recall_decision,
    re_dilution_results,
    re_injection_results,
    reference_complaint_number,
    related_customer,
    related_market,
    repeated_deviation,
    report_delay_justification,
    reserve_sample_observations,
    risk_analysis,
    root_cause_category,
    root_cause_sub_category,
    sample_number,
    segregation_of_the_material,
    sfg_code,
    specification_number,
    stability_condition,
    stability_protocol_number,
    stability_review_comments,
    stability_time_point,
    status,
    status_end_date,
    status_start_date,
    stp_number,
    sub_area,
    supporting_documents,
    suspension_of_the_operation,
    title,
    workflow_status
FROM public.investigation_ai_sample_test;

select * from public.dim_event;

-- DIM_RCI
CREATE TABLE IF NOT EXISTS public.dim_rci (
    rci_key INT PRIMARY KEY,
    reference_number TEXT, 
    root_cause_summary TEXT, 
    root_cause_conclusion TEXT
);

INSERT INTO public.dim_rci (
    rci_key,
    reference_number, 
    root_cause_summary, 
    root_cause_conclusion
)
select DISTINCT
    rci_id as rci_key,
    reference_number, 
    root_cause_summary, 
    root_cause_conclusion
FROM public.investigation_ai_sample_test
where 
 rci_id is not null;

SELECT COUNT(*)
FROM public.dim_rci;



-- FACT_QMS_EVENT
CREATE TABLE IF NOT EXISTS public.fact_qms_event (
    composite_primary_key TEXT PRIMARY KEY,

    date_opened TIMESTAMP,
    date_closed TIMESTAMP,
    due_date TIMESTAMP,
    closed_on TIMESTAMP,

    location_key INTEGER,
    event_classification_key INTEGER,
    equipment_key INTEGER,
    department_key INTEGER,
    product_key INTEGER,
    deviation_id INTEGER,
    batch_key INTEGER,
    investigator_key INTEGER,
    rci_key INTEGER,

    time_elapsed INTEGER,
    pg_updated_at_timestamp TIMESTAMP,

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

INSERT INTO public.fact_qms_event (
    composite_primary_key,
    date_opened,
    date_closed,
    due_date,
    closed_on,
    location_key,
    event_classification_key,
    equipment_key,
    department_key,
    product_key,
    deviation_id,
    batch_key,
    investigator_key,
    rci_key,
    time_elapsed,
    pg_updated_at_timestamp
)
SELECT
    iast.composite_primary_key,
    iast.date_opened,
    iast.date_closed,
    iast.due_date,
    iast.closed_on,
    l.location_key,
    ec.event_classification_key,
    eq.equipment_key,
    d.department_key,
    p.product_key,
    e.deviation_id,
    b.batch_key,
    i.investigator_key,
    r.rci_key,
    iast.time_elapsed,
    iast.pg_updated_at_timestamp
FROM public.investigation_ai_sample_test iast
LEFT JOIN public.dim_location l
    ON iast.location = l.location
LEFT JOIN public.dim_event_classification ec
    ON iast.qe_type = ec.qe_type
LEFT JOIN public.dim_equipment eq
    ON iast.instrument_equipment = eq.instrument_equipment
   AND iast.instrument_equipment_id = eq.instrument_equipment_id
LEFT JOIN public.dim_department d
    ON iast.department = d.department
LEFT JOIN public.dim_product p
    ON iast.name_of_material = p.name_of_material
LEFT JOIN public.dim_event e
    ON iast.deviation_id = e.deviation_id
LEFT JOIN public.dim_batch b
    ON iast.batch_no = b.batch_no
LEFT JOIN public.dim_investigator i
    ON iast.assignee_id = i.investigator_key
LEFT JOIN public.dim_rci r
    ON iast.rci_id = r.rci_key;

SELECT COUNT(*)
FROM public.fact_qms_event;