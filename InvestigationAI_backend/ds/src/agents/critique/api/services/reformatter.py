from typing import Any, Dict, Optional


def reformat_to_investigation_plan_payload(
    extracted: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Converts merged section-wise extraction output into
    FE-ready InvestigationPlanPayload.

    NOTES:
    - No validation is performed
    - Missing or empty values are normalized to None
    - Always returns a payload if extraction succeeds
    """

    def normalize(value: Any) -> Optional[Any]:
        if value in ("", [], {}, None):
            return None
        return value
    
    # --------------------------------------------------
    # Section 1.1 – Event Description
    # --------------------------------------------------
    section_1_1 = extracted.get("EventDescription", {})
    rci_header = section_1_1.get("rci_header", {})
    sections = section_1_1.get("sections", [])

    problem_statement = None
    for section in sections:
        if section.get("section_type") == "problem_statement":
            fields = section.get("fields", [])
            if fields:         
                problem_statement = [
                    f.get("value") for f in fields if f.get("value")
                ]
            break
        
    for statement in problem_statement:
        problem_statement_string += statement if isinstance(statement, str) else statement[0]

    event_description = {
        "section": "1.1",
        "title": section_1_1.get("title"),
        "data": {
            "rciNumber": normalize(rci_header.get("rci_number")),
            "rciOwner": normalize(rci_header.get("rci_owner")),
            "rciInitiatedOn": normalize(rci_header.get("initiated_on")),
            "parentRecord": normalize(rci_header.get("parent_record")),
            "problemStatement": normalize(problem_statement_string),          
            "additionalSections": [
                        {
                            "type": s.get("section_type"),
                            "title": s.get("title"),
                            "fields": s.get("fields", []),
                        }
                        for s in sections
                        if s.get("section_type") != "problem_statement"
                    ],

        },
    }

    # --------------------------------------------------
    # Section 1.2 – Prerequisites
    # --------------------------------------------------
    section_1_2 = extracted.get("prerequisites", {})

    prerequisites_data = []
    for item in section_1_2.get("items", []):
        selected_label = None
        for choice in item.get("choices", []):
            if choice.get("selected"):
                selected_label = choice.get("label")
                break

        prerequisites_data.append({
            "text": normalize(item.get("prerequisite")),
            "response": normalize(selected_label),
            "explanation": normalize(item.get("explanation")),
        })

    prerequisites = {
        "section": "1.2",
        "title": section_1_2.get("title"),
        "data": prerequisites_data,
    }

    # --------------------------------------------------
    # Section 2.1 – Task Assignments
    # --------------------------------------------------
    section_2_1 = extracted.get("taskassignments", {})

    task_items = []
    for item in section_2_1.get("items", []):
        task_items.append({
            "tick": normalize((item.get("task") or "").strip()),
            "task": normalize(item.get("status")),
            "responsible_person": normalize(item.get("responsible_person")),
            "selected": bool(item.get("selected", False)),
            "critique": None,  # Not present in source document
            "mandatory": to_bool(item.get("mandatory", False)),
        })

    task_assignments = {
        "section": "2.1",
        "title": section_2_1.get("title"),
        "data": task_items,
    }

    # --------------------------------------------------
    # Section 2.2 – SignOff
    # --------------------------------------------------
    section_2_2 = extracted.get("signoff", {})

    signoff_items = []
    for signatory in section_2_2.get("signatories", []):
        signoff_items.append({
            "role": normalize(signatory.get("role")),
            "name": normalize(signatory.get("name")),
        })

    signoff_payload = {
        "section": "2.2",
        "title": section_2_2.get("title"),
        "data": signoff_items,
}

    # --------------------------------------------------
    # Final FE Payload
    # --------------------------------------------------
    return {
        "eventDescription": event_description,
        "prerequisites": prerequisites,
        "taskAssignments": task_assignments,
        "signOff": signoff_payload
    }



def to_bool(val):
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.strip().lower() in {"yes", "true", "1"}
    return None