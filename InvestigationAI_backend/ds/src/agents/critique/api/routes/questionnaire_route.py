from fastapi import APIRouter, HTTPException, status
from src.agents.critique.api.services.questionnaire_service import gen_questions
from src.agents.critique.api.schemas import QuestionnaireRequest
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/questionnaire', tags=['critique'])
@router.post("/generate_questionnaire")
async def generate_questionnaire(
    body: QuestionnaireRequest,
):
    try:
        questions_model = await gen_questions(
            event_type=body.event_type,
            problem_statement=body.problem_statement,
            preliminary_findings=body.preliminary_findings,
        )
        logger.info("Questionnaire generated successfully")
        questions = questions_model.model_dump()["question"]
        return questions

    except HTTPException:
        # Let FastAPI handle known HTTP errors
        raise

    except Exception:
        logger.exception("Questionnaire generation failed at API layer")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate questions",
        )