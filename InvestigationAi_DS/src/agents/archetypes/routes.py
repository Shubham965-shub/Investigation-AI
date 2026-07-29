"""
API routes for archetype library management.

Evidence Collection:
  GET  /archetypes/evidence           — list all archetypes with their evidence items
  POST /archetypes/evidence           — add a new archetype (skipped if name already exists)

Interview Questionnaire:
  GET  /archetypes/questionnaire      — list all archetypes with their questions
  POST /archetypes/questionnaire      — add a new archetype (skipped if name already exists)
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from src.utils.deps import get_db_pool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/archetypes", tags=["Archetype Library"])

# ── Pydantic schemas ────────────────────────────────────────────────────────

class EvidenceItem(BaseModel):
    id: int
    description: str

class EvidenceArchetypeResponse(BaseModel):
    id: int
    name: str
    definition: Optional[str]
    evidence: List[EvidenceItem]

class NewEvidenceArchetypeRequest(BaseModel):
    name: str
    definition: Optional[str] = None
    evidence: List[str]

class QuestionItem(BaseModel):
    id: int
    description: str

class QuestionnaireArchetypeResponse(BaseModel):
    id: int
    name: str
    definition: Optional[str]
    questions: List[QuestionItem]

class NewQuestionnaireArchetypeRequest(BaseModel):
    name: str
    definition: Optional[str] = None
    questions: List[str]

class AddArchetypeResponse(BaseModel):
    created: bool
    id: int
    name: str
    message: str

# ── Helpers ─────────────────────────────────────────────────────────────────

async def _get_type_id(conn, type_name: str) -> int:
    row = await conn.fetchrow(
        "SELECT id FROM archetype_type WHERE name = $1", type_name
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Archetype type '{type_name}' not found in database. Run the populate script first.",
        )
    return row["id"]


def _group_archetype_rows(rows) -> list[dict]:
    """Collapse JOIN rows into archetype objects."""
    archetypes: dict[int, dict] = {}
    for row in rows:
        aid = row["archetype_id"]
        if aid not in archetypes:
            archetypes[aid] = {
                "id": aid,
                "name": row["archetype_name"],
                "definition": row["definition"],
                "items": [],
            }
        if row["item_id"]:
            archetypes[aid]["items"].append({
                "id": row["item_id"],
                "description": row["item_description"],
            })
    return list(archetypes.values())


# ── Evidence Collection endpoints ───────────────────────────────────────────

@router.get(
    "/evidence",
    response_model=List[EvidenceArchetypeResponse],
    summary="List all Evidence Collection archetypes",
)
async def list_evidence_archetypes() -> List[EvidenceArchetypeResponse]:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        type_id = await _get_type_id(conn, "Evidence Collection")
        rows = await conn.fetch(
            """
            SELECT
                a.id   AS archetype_id,
                a.name AS archetype_name,
                a.definition,
                e.id   AS item_id,
                e.description AS item_description
            FROM archetype a
            LEFT JOIN evidence e ON e.archetype_id = a.id
            WHERE a.archetype_type_id = $1
            ORDER BY a.id, e.id
            """,
            type_id,
        )

    grouped = _group_archetype_rows(rows)
    return [
        EvidenceArchetypeResponse(
            id=g["id"],
            name=g["name"],
            definition=g["definition"],
            evidence=[EvidenceItem(**item) for item in g["items"]],
        )
        for g in grouped
    ]


@router.post(
    "/evidence",
    response_model=AddArchetypeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new Evidence Collection archetype (no-op if name already exists)",
)
async def add_evidence_archetype(body: NewEvidenceArchetypeRequest) -> AddArchetypeResponse:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        type_id = await _get_type_id(conn, "Evidence Collection")

        existing = await conn.fetchrow(
            "SELECT id FROM archetype WHERE name = $1 AND archetype_type_id = $2",
            body.name, type_id,
        )
        if existing:
            return AddArchetypeResponse(
                created=False,
                id=existing["id"],
                name=body.name,
                message="Archetype already exists — no changes made.",
            )

        async with conn.transaction():
            archetype_id = await conn.fetchval(
                """
                INSERT INTO archetype (name, definition, archetype_type_id)
                VALUES ($1, $2, $3)
                RETURNING id
                """,
                body.name, body.definition, type_id,
            )
            if body.evidence:
                await conn.executemany(
                    "INSERT INTO evidence (description, archetype_id) VALUES ($1, $2)",
                    [(item, archetype_id) for item in body.evidence],
                )

    logger.info("Created Evidence Collection archetype '%s' (id=%d)", body.name, archetype_id)
    return AddArchetypeResponse(
        created=True,
        id=archetype_id,
        name=body.name,
        message=f"Archetype created with {len(body.evidence)} evidence item(s).",
    )


# ── Interview Questionnaire endpoints ───────────────────────────────────────

@router.get(
    "/questionnaire",
    response_model=List[QuestionnaireArchetypeResponse],
    summary="List all Interview Questionnaire archetypes",
)
async def list_questionnaire_archetypes() -> List[QuestionnaireArchetypeResponse]:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        type_id = await _get_type_id(conn, "Interview Questionnaire")
        rows = await conn.fetch(
            """
            SELECT
                a.id   AS archetype_id,
                a.name AS archetype_name,
                a.definition,
                q.id   AS item_id,
                q.description AS item_description
            FROM archetype a
            LEFT JOIN interview_questionnaire q ON q.archetype_id = a.id
            WHERE a.archetype_type_id = $1
            ORDER BY a.id, q.id
            """,
            type_id,
        )

    grouped = _group_archetype_rows(rows)
    return [
        QuestionnaireArchetypeResponse(
            id=g["id"],
            name=g["name"],
            definition=g["definition"],
            questions=[QuestionItem(**item) for item in g["items"]],
        )
        for g in grouped
    ]


@router.post(
    "/questionnaire",
    response_model=AddArchetypeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add a new Interview Questionnaire archetype (no-op if name already exists)",
)
async def add_questionnaire_archetype(body: NewQuestionnaireArchetypeRequest) -> AddArchetypeResponse:
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        type_id = await _get_type_id(conn, "Interview Questionnaire")

        existing = await conn.fetchrow(
            "SELECT id FROM archetype WHERE name = $1 AND archetype_type_id = $2",
            body.name, type_id,
        )
        if existing:
            return AddArchetypeResponse(
                created=False,
                id=existing["id"],
                name=body.name,
                message="Archetype already exists — no changes made.",
            )

        async with conn.transaction():
            archetype_id = await conn.fetchval(
                """
                INSERT INTO archetype (name, definition, archetype_type_id)
                VALUES ($1, $2, $3)
                RETURNING id
                """,
                body.name, body.definition, type_id,
            )
            if body.questions:
                await conn.executemany(
                    "INSERT INTO interview_questionnaire (description, archetype_id) VALUES ($1, $2)",
                    [(q, archetype_id) for q in body.questions],
                )

    logger.info("Created Interview Questionnaire archetype '%s' (id=%d)", body.name, archetype_id)
    return AddArchetypeResponse(
        created=True,
        id=archetype_id,
        name=body.name,
        message=f"Archetype created with {len(body.questions)} question(s).",
    )
