from pydantic import BaseModel
from typing import List

class HypothesisTask(BaseModel):
    hypothesis: str
    task: str

class RootCauseCategory(BaseModel):
    category: str
    gaps: List[str]
    items: List[HypothesisTask]
    assumptions: List[str]

class rootCauseAdvisoryResponse(BaseModel):
    root_cause_categories: List[RootCauseCategory]