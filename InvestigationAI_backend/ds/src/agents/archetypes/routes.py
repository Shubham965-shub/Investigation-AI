"""
API routes for archetype library management.

Evidence Collection:
  GET  /archetypes/evidence           — list all archetypes with their evidence items
  POST /archetypes/evidence           — add a new archetype (skipped if name already exists)
  POST /archetypes/evidence/upload    — bulk-load the Evidence Library Excel (per-archetype upsert)

Interview Questionnaire:
  GET  /archetypes/questionnaire      — list all archetypes with their questions
  POST /archetypes/questionnaire      — add a new archetype (skipped if name already exists)
  POST /archetypes/questionnaire/upload — bulk-load the Interview Questionnaire Excel (per-archetype upsert)
"""

from __future__ import annotations

import io
import logging
from typing import Any, List, Optional

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile, status
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

class LibraryUploadResponse(BaseModel):
    status: str
    message: str
    archetypes_processed: List[str]
    archetypes_created: int
    archetypes_updated: int
    items_created: int

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


def _find_col(possible_names: List[str], df_cols: List[Any]) -> Optional[Any]:
    normalized = {name.strip().lower() for name in possible_names}
    for col in df_cols:
        if str(col).strip().lower() in normalized:
            return col
    return None


def _find_sheet(sheet_names: List[str], candidates: List[str]) -> Optional[str]:
    normalized = {c.strip().lower() for c in candidates}
    for name in sheet_names:
        if name.strip().lower() in normalized:
            return name
    return None


async def _upload_library_excel(
    *,
    file: UploadFile,
    type_name: str,
    sheet_candidates: List[str],
    name_col_candidates: List[str],
    definition_col_candidates: List[str],
    item_col_candidates: List[str],
    item_table: str,
) -> LibraryUploadResponse:
    """Shared bulk-upload logic for the Evidence and Interview Questionnaire
    libraries: one flat sheet, archetype name repeated/blank-filled down
    column A, one item (evidence description / question) per row.

    Each archetype is upserted by name: its child items are replaced
    wholesale so re-uploading a corrected file reflects the new content,
    matching the per-archetype replace semantics of POST /rci/upload.
    """
    filename = (file.filename or "").strip()
    suffix = filename.split(".")[-1].lower() if "." in filename else ""
    if suffix not in ["xlsx", "xls"]:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only Excel (.xlsx, .xls) files are supported.",
        )

    try:
        contents = await file.read()
        excel_file = pd.ExcelFile(io.BytesIO(contents))

        sheet_name = _find_sheet(excel_file.sheet_names, sheet_candidates)
        if not sheet_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"None of the expected sheets {sheet_candidates} were found. "
                    f"Sheets present: {excel_file.sheet_names}"
                ),
            )

        df = pd.read_excel(excel_file, sheet_name=sheet_name, header=0)
        df.columns = [str(col).strip() for col in df.columns]

        name_col = _find_col(name_col_candidates, df.columns)
        definition_col = _find_col(definition_col_candidates, df.columns)
        item_col = _find_col(item_col_candidates, df.columns)

        if not name_col or not item_col:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    f"Could not find required columns in sheet '{sheet_name}'. "
                    f"Looked for name in {name_col_candidates}, item in {item_col_candidates}. "
                    f"Columns present: {list(df.columns)}"
                ),
            )

        # Merged/blank-continuation cells: forward-fill the archetype name
        # (and definition, if present) down to the item rows beneath them.
        df[name_col] = df[name_col].ffill()
        if definition_col:
            df[definition_col] = df[definition_col].ffill()

        df = df.dropna(subset=[item_col])
        if df.empty:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"No usable rows found in sheet '{sheet_name}'.",
            )

        archetypes_processed: List[str] = []
        archetypes_created = 0
        archetypes_updated = 0
        items_created = 0

        pool = await get_db_pool()
        async with pool.acquire() as conn:
            type_id = await _get_type_id(conn, type_name)

            async with conn.transaction():
                for archetype_name, group in df.groupby(name_col):
                    archetype_name = str(archetype_name).strip()
                    if not archetype_name:
                        continue

                    definition_value = None
                    if definition_col:
                        defs = group[definition_col].dropna().astype(str)
                        if not defs.empty:
                            definition_value = defs.iloc[0].strip() or None

                    existing = await conn.fetchrow(
                        """
                        SELECT id FROM archetype
                        WHERE LOWER(name) = LOWER($1) AND archetype_type_id = $2
                        """,
                        archetype_name, type_id,
                    )

                    if existing:
                        archetype_id = existing["id"]
                        await conn.execute(
                            "UPDATE archetype SET definition = COALESCE($1, definition) WHERE id = $2",
                            definition_value, archetype_id,
                        )
                        await conn.execute(
                            f"DELETE FROM {item_table} WHERE archetype_id = $1",
                            archetype_id,
                        )
                        archetypes_updated += 1
                    else:
                        archetype_id = await conn.fetchval(
                            """
                            INSERT INTO archetype (name, definition, archetype_type_id)
                            VALUES ($1, $2, $3)
                            RETURNING id
                            """,
                            archetype_name, definition_value, type_id,
                        )
                        archetypes_created += 1

                    archetypes_processed.append(archetype_name)

                    item_values = [
                        str(v).strip() for v in group[item_col].tolist()
                        if str(v).strip() and str(v).strip().lower() != "nan"
                    ]
                    if item_values:
                        await conn.executemany(
                            f"INSERT INTO {item_table} (description, archetype_id) VALUES ($1, $2)",
                            [(v, archetype_id) for v in item_values],
                        )
                        items_created += len(item_values)

        return LibraryUploadResponse(
            status="success",
            message=f"Successfully imported '{type_name}' templates from {filename}.",
            archetypes_processed=archetypes_processed,
            archetypes_created=archetypes_created,
            archetypes_updated=archetypes_updated,
            items_created=items_created,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to parse and upload '%s' library", type_name)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process upload: {str(e)}",
        )
    finally:
        await file.close()


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


@router.post(
    "/evidence/upload",
    response_model=LibraryUploadResponse,
    summary="Bulk-load the Evidence Library Excel (per-archetype upsert)",
)
async def upload_evidence_library(file: UploadFile = File(...)) -> LibraryUploadResponse:
    """
    Expects a sheet named 'Evidence Library' with columns:
    Failure Type | ... | Description/Definition | Evidence to Collect
    (archetype name and definition may be blank-filled across their item rows).
    """
    return await _upload_library_excel(
        file=file,
        type_name="Evidence Collection",
        sheet_candidates=["Evidence Library"],
        name_col_candidates=["Failure Type", "Failure Mode"],
        definition_col_candidates=["Description/Definition", "Definition"],
        item_col_candidates=["Evidence to Collect", "Evidence"],
        item_table="evidence",
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


@router.post(
    "/questionnaire/upload",
    response_model=LibraryUploadResponse,
    summary="Bulk-load the Interview Questionnaire Excel (per-archetype upsert)",
)
async def upload_questionnaire_library(file: UploadFile = File(...)) -> LibraryUploadResponse:
    """
    Expects a sheet named 'Events' with columns:
    Error type | Definition | Questions
    (archetype name and definition may be blank-filled across their item rows).
    """
    return await _upload_library_excel(
        file=file,
        type_name="Interview Questionnaire",
        sheet_candidates=["Events"],
        name_col_candidates=["Error type", "Failure Type"],
        definition_col_candidates=["Definition"],
        item_col_candidates=["Questions", "Question"],
        item_table="interview_questionnaire",
    )
