"""
API routes for evidence collection.
"""

import logging

from fastapi import APIRouter, HTTPException, status

from src.agents.evidence_collection.graph import evidence_collection_graph, EvidenceCollectionState
from src.agents.evidence_collection.schemas import EvidenceCollectionRequest, EvidenceCollectionResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/evidence", tags=["Evidence Collection"])


@router.post(
    "/collect",
    response_model=EvidenceCollectionResponse,
    summary="Collect evidence requirements for a quality event",
)
async def collect_evidence(request: EvidenceCollectionRequest) -> EvidenceCollectionResponse:
    """
    Analyse a quality event and return the list of evidence to collect.

    **Supported event types:** Deviation, OOS, OOT, OOS/OOT, Market Complaint

    **Process:**
    1. Validates trackwise fields against the event type schema.
    2. Maps the failure type to the closest existing archetype with a confidence score.
    3. High confidence (≥ 0.7): fetches and rephrases archetype evidence.
       Low confidence (< 0.7): searches historical incidents and infers evidence via LLM.
    4. Returns the complete evidence list with archetype match details.
    """
    try:
        state = EvidenceCollectionState(
            trackwise_fields=request.trackwise_fields,
            event_type=request.event_type,
        )
        logger.info(f"Processing evidence collection for event_type: {request.event_type}")

        final_state = await evidence_collection_graph.ainvoke(state)
        result = final_state.get("final_result")

        return EvidenceCollectionResponse(
            event_type=result["event_type"],
            failure_type=result["failure_type"],
            archetype=result["archetype"],
            evidence=result["evidence"],
            total_evidence_count=result["total_evidence_count"],
        )

    except Exception as e:
        logger.exception("Error in evidence collection")
        error_msg = str(e)
        if "Invalid trackwise fields" in error_msg or "ValidationError" in error_msg:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid trackwise fields: {error_msg}",
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process evidence collection: {error_msg}",
        )
