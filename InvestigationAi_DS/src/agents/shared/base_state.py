from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class BaseArchetypeState:
    """Common state fields shared by all archetype-mapping workflows."""
    ARCHETYPE_TYPE = None  # Should be overridden by subclasses
    trackwise_fields: Dict[str, Any]
    event_type: str
    failure_type: Optional[str] = None
    all_archetypes: List[Dict[str, Any]] = field(default_factory=list)
    mapped_archetype: Optional[Dict[str, Any]] = None
    reasoning: Optional[str] = None
    is_new_archetype: bool = False
    confidence_score: Optional[float] = None
    final_result: Optional[Dict[str, Any]] = None
    # Historical search — used by the low-confidence fallback path in all workflows
    search_query: Optional[str] = None
    search_results: Optional[List[Dict[str, Any]]] = None
