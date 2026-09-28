"""
API routes for interview questionnaire generation.
"""

import logging

from fastapi import APIRouter, HTTPException, status

from src.agents.interview_questionnaire.graph import (
    interview_questionnaire_graph,
    InterviewQuestionCollectionState,
)
from src.agents.interview_questionnaire.schemas import (
    QuestionCollectionRequest,
    QuestionCollectionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/interview", tags=["Interview Questionnaire"])


@router.post(
    "/questionnaire",
    response_model=QuestionCollectionResponse,
    summary="Generate interview questionnaire for a quality event",
)
async def generate_questionnaire(request: QuestionCollectionRequest) -> QuestionCollectionResponse:
    """
    Analyse a quality event and return a list of contextualised interview questions.

    **Supported event types:** Deviation, OOS, OOT, OOS/OOT, Market Complaint

    **Process:**
    1. Validates trackwise fields against the event type schema.
    2. Maps the failure type to the closest existing archetype with a confidence score.
    3. Fetches interview questions for the matched archetype.
    4. Rephrases questions to be contextual to the specific event details.
    5. Returns the complete questionnaire with archetype match details.
    """
    try:
        state = InterviewQuestionCollectionState(
            trackwise_fields=request.trackwise_fields,
            event_type=request.event_type,
            rci_id=request.rci_id,
        )
        logger.info(f"Processing questionnaire for event_type: {request.event_type}")

        final_state = await interview_questionnaire_graph.ainvoke(state)
        result = final_state.get("final_result")

        return QuestionCollectionResponse(
            event_type=result["event_type"],
            failure_type=result["failure_type"],
            archetype=result["archetype"],
            questions=result["questions"],
            total_questions_count=result["total_questions_count"],
        )

    except Exception as e:
        logger.exception("Error in questionnaire generation")
        error_msg = str(e)
        if "Invalid trackwise fields" in error_msg or "ValidationError" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid trackwise fields: {error_msg}",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process questionnaire: {error_msg}",
        )
