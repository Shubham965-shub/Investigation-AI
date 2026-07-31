from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.agents.shared.base_state import BaseArchetypeState


@dataclass
class EvidenceCollectionState(BaseArchetypeState):
    """State for the evidence collection workflow."""

    ARCHETYPE_TYPE: str = "Evidence Collection"
    evidence_list: List[Dict[str, Any]] = field(default_factory=list)
    rephrased_evidence: List[Dict[str, Any]] = field(default_factory=list)
    is_exhaustive: bool = False
    new_evidence: List[str] = field(default_factory=list)
