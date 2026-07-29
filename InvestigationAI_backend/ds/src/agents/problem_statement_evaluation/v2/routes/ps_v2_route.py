"""
V2 Routes for structured problem statement generation from trackwise fields.
"""

from fastapi import APIRouter, HTTPException, status
import logging

from src.agents.problem_statement_evaluation.v2.schemas import (
    ProblemStatementGenerationRequest,
    ProblemStatementGenerationResponse,
)
from src.agents.problem_statement_evaluation.v2.services.problem_statement_generator import (
    generate_problem_statement,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ps/v2", tags=["Problem Statement Evaluation V2"])


@router.post(
    "/generate",
    response_model=ProblemStatementGenerationResponse,
    summary="Generate structured problem statement from trackwise fields",
)
async def generate_problem_statement_endpoint(
    request: ProblemStatementGenerationRequest,
) -> ProblemStatementGenerationResponse:
    """
    Generate a structured problem statement from trackwise fields using LLM.
    
    Supported event types:
    - Deviation
    - OOS (Out of Specification)
    - OOT (Out of Trend)
    - Market Complaint
    """
    try:
        result = await generate_problem_statement(
            event_type=request.event_type,
            trackwise_fields=request.trackwise_fields,
        )


        print("result", result)
        
        return ProblemStatementGenerationResponse(
            event_type=request.event_type,
            problem_statement=result["problem_statement"]
        )
    
    except Exception as e:
        logger.exception("Failed to generate problem statement")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate problem statement",
        )
