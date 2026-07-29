"""endpoint for getting event record summaries"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from src.utils.deps import get_db_pool
from src.agents.search_agent.api.schemas import (
    CumulativeSummaryRequest,
    SynthType,
    RCSEvent
)
from src.agents.search_agent.api.services.summary_synthesizer import get_synth_summary, normalize_ids, format_response_for_ui
from src.config.settings import settings


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/summary", tags=["search"])

@router.post("/root_cause_synthesizer")
async def summary_root_cause_synthesizer(
    body: CumulativeSummaryRequest,
    pool=Depends(get_db_pool),
):
    ids, use_text = normalize_ids(body.deviation_id)

    try:
        async with pool.acquire() as db_conn:

            join_condition = (
                f'sv."{settings.COLUMN_ID}"::text = s."{settings.SUMMARY_ID_COLUMN}"::text'
                if use_text
                else f'sv."{settings.COLUMN_ID}" = s."{settings.SUMMARY_ID_COLUMN}"'
            )

            where_clause = (
                f'sv."{settings.COLUMN_ID}" = ANY($1::text[])'
                if use_text
                else f'sv."{settings.COLUMN_ID}" = ANY($1)'
            )

            query = f"""
            SELECT
                sv.*,
                s."{settings.SUMMARY_COL_EVENT_DESCRIPTION}"   AS "{settings.SUMMARY_COL_EVENT_DESCRIPTION}",
                s."{settings.SUMMARY_COL_ROOT_CAUSE}"          AS "{settings.SUMMARY_COL_ROOT_CAUSE}",
                s."{settings.SUMMARY_COL_CAPA}"                AS "{settings.SUMMARY_COL_CAPA}",
                s."{settings.SUMMARY_COL_CAPA_DATE}" AS "{settings.SUMMARY_COL_CAPA_DATE}"
            FROM "{settings.SEARCH_TABLE}" sv
            LEFT JOIN "{settings.SUMMARY_TABLE}" s
            ON {join_condition}
            WHERE {where_clause}
            """

            rows = await db_conn.fetch(query, ids)

    except Exception as exc:
        logger.exception("Database access failure")
        raise HTTPException(status_code=500, detail="Database query failed") from exc

    event_records = []

    try:
        for row in rows:
            row_dict = dict(row)
            row_lower = {k.lower(): v for k, v in row_dict.items()}

            def ci_get(col_name: str):
                return row_lower.get(col_name.lower(), "")
            event_records.append(
                RCSEvent(
                    deviation_id=ci_get(settings.COLUMN_ID),
                    description=ci_get(settings.SUMMARY_COL_EVENT_DESCRIPTION),
                    root_cause_category=ci_get(settings.COLUMN_CATEGORY),
                    root_cause_summary=ci_get(settings.SUMMARY_COL_ROOT_CAUSE),
                    site=ci_get(settings.COLUMN_LOCATION)

                )
            )
    except Exception as exc:
        logger.exception("Failed to normalize DB rows into RCSEvent records")
        raise HTTPException(status_code=500, detail="Data transformation error") from exc

    try:
        logger.info(f"input has {len(event_records)} records")
        result = await get_synth_summary(records=event_records, synth_type="rc")
        final_response = format_response_for_ui(synth_type=SynthType.RC,response=result)
        return final_response
    except Exception as exc:
        logger.exception("Root cause synthesis generation failed")
        raise HTTPException(status_code=500, detail="Root cause synthesis failed") from exc
