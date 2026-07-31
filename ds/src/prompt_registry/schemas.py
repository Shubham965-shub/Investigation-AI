from typing import List, Optional
from pydantic import BaseModel


class PromptVersionOut(BaseModel):
    name: str
    version: str
    description: str
    created_at: str
    is_active: bool
    template: str


class PromptSummary(BaseModel):
    name: str
    active_version: Optional[str]
    total_versions: int


class CreateVersionRequest(BaseModel):
    template: str
    description: Optional[str] = None


class ActivateVersionRequest(BaseModel):
    version: str
