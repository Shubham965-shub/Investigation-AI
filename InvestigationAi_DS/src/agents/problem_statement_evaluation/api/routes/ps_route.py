import tempfile, shutil
from fastapi import UploadFile, File, HTTPException, status, APIRouter
from fastapi.responses import JSONResponse
from docx import Document
from pathlib import Path
from src.utils.deps import get_db_pool, get_llm_client
from src.agents.problem_statement_evaluation.api.services.evaluation_service import evaluate_ps
from src.agents.problem_statement_evaluation.api.schemas import EvaluateResponse, EvaluateRequest, ImmediateActionsResponse, ChecklistItem, CheckList, ImprovementSuggestionList, ImprovementSuggestion
from src.agents.problem_statement_evaluation.api.services.action_service import immediate_actions
from src.agents.critique.api.services.extraction import detect_backbone_table, walk_tables_dedup_by_xml, df_to_row_dicts, extract_problem_from_backbone_rows

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/ps', tags=['Problem Statement Evaluation'])

@router.post('/evaluate', response_model=EvaluateResponse)
async def evaluation(problem_statement: EvaluateRequest):
    event = problem_statement.event_type
    narrative = problem_statement.narrative
    try:
        raw = await evaluate_ps(query=narrative, event_type=event)
        raw_checklist = raw.get("checklist", []) or []
        checklist_obj = CheckList(
            response=[
                ci if isinstance(ci, ChecklistItem) else ChecklistItem(**ci)
                for ci in raw_checklist
            ]
        )

        raw_suggestions = raw.get("suggestions")
        if isinstance(raw_suggestions, ImprovementSuggestionList):
            suggestions_obj = raw_suggestions
        else:
            if isinstance(raw_suggestions, dict) and "suggestions" in raw_suggestions:
                suggestions_list = raw_suggestions["suggestions"]
            else:
                suggestions_list = raw_suggestions or []
            suggestions_obj = ImprovementSuggestionList(
                suggestions=[
                    s if isinstance(s, ImprovementSuggestion) else ImprovementSuggestion(**s)
                    for s in suggestions_list
                ]
            )

        return JSONResponse({"checklist":checklist_obj.model_dump().get('response'), "suggestions":suggestions_obj.model_dump().get('suggestions')})
    except Exception as exc:
        logger.exception("Failed to run evaluation service")
        raise HTTPException(status_code=500, detail=str(exc))


@router.post(
    "/generate_immediate_actions",
    response_model=ImmediateActionsResponse,
    summary="Return 5 predefined SOP actions based on event_type + 5 LLM-generated actions specific to narration."
)
async def generate_immediate_actions(problem_statement: EvaluateRequest):
    event = problem_statement.event_type
    narrative = problem_statement.narrative
    try:
        return await immediate_actions(query=narrative, event_type=event)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("couldn't generate immediate actions")
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
    

@router.post(
    "/extract/evaluate",
    tags=["extract"],
    response_class=JSONResponse,
    responses={
        200: {"description": "Returns only the Problem Statement from section 1.1"},
        400: {"description": "Extraction failed or no tables/section found"},
        415: {"description": "Unsupported media type (must be .docx)"},
        500: {"description": "Internal server error"},
    },
)
async def extract_evaluate(file: UploadFile = File(...), event_type: str = None) -> JSONResponse:
    """
    Accept a DOCX and return only the Problem Statement (split into items).
    """
    event = event_type
    filename = (file.filename or "").lower()
    if not filename.endswith(".docx"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type. Please upload a .docx file.",
        )

    # Save upload to a temp file
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = Path(tmp.name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to buffer upload: {e}")

    try:
        # Open DOCX
        doc = Document(tmp_path)
        if not doc.tables:
            raise HTTPException(status_code=400, detail="No tables found in document.")

        # Build all_tables { name -> DataFrame }
        all_tables = {}
        for i, t in enumerate(doc.tables, start=1):
            all_tables.update(walk_tables_dedup_by_xml(t, prefix=f"Table{i}"))

        # Auto-detect the backbone (Table1-like)
        bb_name, backbone_df = detect_backbone_table(all_tables)
        if backbone_df is None:
            raise HTTPException(status_code=400, detail="Backbone table (sections) not detected.")

        # Convert backbone df to row-dicts
        table1_rows = df_to_row_dicts(backbone_df)

        # Extract problem statement (label-first, sentinel-aware)
        problems = extract_problem_from_backbone_rows(table1_rows)
        problem_statement = ""

        for problem in problems['items']:
            problem_statement = problem_statement + '\n' + problem

        try:

            raw = await evaluate_ps(query=problem_statement, event_type=event)
            raw_checklist = raw.get("checklist", []) or []
            checklist_obj = CheckList(
                response=[
                    ci if isinstance(ci, ChecklistItem) else ChecklistItem(**ci)
                    for ci in raw_checklist
                ]
            )

            raw_suggestions = raw.get("suggestions")
            if isinstance(raw_suggestions, ImprovementSuggestionList):
                suggestions_obj = raw_suggestions
            else:
                if isinstance(raw_suggestions, dict) and "suggestions" in raw_suggestions:
                    suggestions_list = raw_suggestions["suggestions"]
                else:
                    suggestions_list = raw_suggestions or []
                suggestions_obj = ImprovementSuggestionList(
                    suggestions=[
                        s if isinstance(s, ImprovementSuggestion) else ImprovementSuggestion(**s)
                        for s in suggestions_list
                    ]
                )
        except Exception as exc:
            logger.exception("Failed to run evaluation service")
            raise HTTPException(status_code=500, detail=str(exc))

        return JSONResponse({"checklist":checklist_obj.model_dump().get('response'), "suggestions":suggestions_obj.model_dump().get('suggestions')})
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction error: {e}")
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass

@router.post(
    "/extract/generate_immediate_actions",
    tags=["extract_generate_immediate_actions"],
    response_class=JSONResponse,
    responses={
        200: {"description": "Returns only the Problem Statement from section 1.1"},
        400: {"description": "Extraction failed or no tables/section found"},
        415: {"description": "Unsupported media type (must be .docx)"},
        500: {"description": "Internal server error"},
    },
)
async def extract_generate_immediate_actions(file: UploadFile = File(...), event_type: str = None) -> JSONResponse:
    """
    Accept a DOCX and return only the Problem Statement (split into items).
    """
    event = event_type
    filename = (file.filename or "").lower()
    if not filename.endswith(".docx"):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported file type. Please upload a .docx file.",
        )

    # Save upload to a temp file
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            shutil.copyfileobj(file.file, tmp)
            tmp_path = Path(tmp.name)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to buffer upload: {e}")

    try:
        # Open DOCX
        doc = Document(tmp_path)
        if not doc.tables:
            raise HTTPException(status_code=400, detail="No tables found in document.")

        # Build all_tables { name -> DataFrame }
        all_tables = {}
        for i, t in enumerate(doc.tables, start=1):
            all_tables.update(walk_tables_dedup_by_xml(t, prefix=f"Table{i}"))

        # Auto-detect the backbone (Table1-like)
        bb_name, backbone_df = detect_backbone_table(all_tables)
        if backbone_df is None:
            raise HTTPException(status_code=400, detail="Backbone table (sections) not detected.")

        # Convert backbone df to row-dicts
        table1_rows = df_to_row_dicts(backbone_df)

        # Extract problem statement (label-first, sentinel-aware)
        problems = extract_problem_from_backbone_rows(table1_rows)
        problem_statement = ""

        for problem in problems['items']:
            problem_statement = problem_statement + '\n' + problem

        try:
            return await immediate_actions(query=problem_statement, event_type=event)
        except NotImplementedError as e:
            raise HTTPException(status_code=501, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            logger.error("couldn't generate immediate actions")
            raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction error: {e}")
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass
