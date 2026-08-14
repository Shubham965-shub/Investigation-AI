from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TaskReportCritiqueState:
    file_path: str
    problem_statement: str = ""
    event_type: str = ""
    task_description: str = ""
    # Optional — identifies which (deviation, task) this upload is for so the previous attempt's
    # accepted recommendations can be looked up. Unset until the backend starts sending them (see
    # ds/src/agents/critique/GAPS.md); when unset, previous_recommendations stays empty and
    # behavior is unchanged from before this field existed.
    deviation_id: Optional[int] = None
    task_index: Optional[int] = None
    # Raw extraction from docx
    raw_paragraphs: List[Dict[str, Any]] = field(default_factory=list)
    raw_tables: List[Dict[str, Any]] = field(default_factory=list)
    # Images with their surrounding context label (which table/section they came from)
    image_context_map: List[Dict[str, Any]] = field(default_factory=list)
    # Structured extraction results
    report_metadata: Dict[str, str] = field(default_factory=dict)
    extracted_tasks: List[Dict[str, Any]] = field(default_factory=list)
    # Vision analysis per evidence photo
    image_analyses: List[Dict[str, Any]] = field(default_factory=list)
    # Previously-accepted recommendations (from the prior attempt on this same task) that are
    # still pending investigator decision — carried in so critique_tasks can check whether this
    # new report addresses them. See fetch_previous_recommendations.
    previous_recommendations: List[str] = field(default_factory=list)
    # Final critique output
    task_critiques: List[Dict[str, Any]] = field(default_factory=list)
    final_result: Optional[Dict[str, Any]] = None
