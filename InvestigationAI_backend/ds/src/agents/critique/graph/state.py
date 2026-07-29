from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TaskReportCritiqueState:
    file_path: str
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
    # Final critique output
    task_critiques: List[Dict[str, Any]] = field(default_factory=list)
    overall_report_summary: str = ""
    final_result: Optional[Dict[str, Any]] = None
