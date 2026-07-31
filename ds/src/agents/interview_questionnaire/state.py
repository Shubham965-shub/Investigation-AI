from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.agents.shared.base_state import BaseArchetypeState


@dataclass
class InterviewQuestionCollectionState(BaseArchetypeState):
    """State for the interview questionnaire workflow."""

    ARCHETYPE_TYPE: str = "Interview Questionnaire"
    question_list: List[Dict[str, Any]] = field(default_factory=list)
    rephrased_questions: List[Dict[str, Any]] = field(default_factory=list)
    new_questions: List[str] = field(default_factory=list)
