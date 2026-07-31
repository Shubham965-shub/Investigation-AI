from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.agents.shared.base_state import BaseArchetypeState


@dataclass
class RciPlanState(BaseArchetypeState):
    """State for the RCI plan workflow."""
    ARCHETYPE_TYPE = "RCI Plan"  # Loads archetypes of this type
    
    # Store original plan template sections fetched from the database
    rci_plan_original: List[Dict[str, Any]] = field(default_factory=list)
    
    # Store rephrased and contextualized plan sections
    rci_plan_rephrased: List[Dict[str, Any]] = field(default_factory=list)
