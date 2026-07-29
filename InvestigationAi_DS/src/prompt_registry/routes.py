"""
REST API for managing prompt versions.

  GET    /prompts                        — list all prompt names + active version
  GET    /prompts/{name}                 — list all versions for a prompt
  GET    /prompts/{name}/{version}       — get one specific version
  POST   /prompts/{name}/versions        — create a new (inactive) version
  PUT    /prompts/{name}/activate        — switch the active version
"""

import logging
from typing import List

from fastapi import APIRouter, HTTPException, status

from src.prompt_registry.schemas import (
    ActivateVersionRequest,
    CreateVersionRequest,
    PromptSummary,
    PromptVersionOut,
)
from src.utils.deps import get_prompt_registry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/prompts", tags=["Prompt Registry"])


@router.get("", response_model=List[PromptSummary])
async def list_prompts():
    registry = get_prompt_registry()
    return registry.list_prompts()


@router.get("/{name:path}/versions", response_model=List[PromptVersionOut])
async def list_versions(name: str):
    registry = get_prompt_registry()
    try:
        return registry.list_versions(name)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{name:path}/{version}", response_model=PromptVersionOut)
async def get_version(name: str, version: str):
    registry = get_prompt_registry()
    try:
        return registry.get_version(name, version)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

#Security risk: creating new prompt versions via API could allow unauthorized users to add malicious prompts. Consider implementing authentication and authorization checks before allowing version creation.
# @router.post("/{name:path}/versions", response_model=PromptVersionOut, status_code=status.HTTP_201_CREATED)
# async def create_version(name: str, body: CreateVersionRequest):
#     registry = get_prompt_registry()
#     try:
#         return registry.create_version(name, body.template, body.description)
#     except Exception as e:
#         logger.exception("Failed to create prompt version")
#         raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put("/{name:path}/activate", status_code=status.HTTP_204_NO_CONTENT)
async def activate_version(name: str, body: ActivateVersionRequest):
    registry = get_prompt_registry()
    try:
        registry.activate_version(name, body.version)
    except KeyError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
