"""endpoint for getting event record capa summaries"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException

from src.utils.deps import get_db_pool
from src.agents.search_agent.api.schemas import (
    CumulativeSummaryRequest,
    SynthType,
    CAPAEvent
)
from src.agents.search_agent.api.services.summary_synthesizer import get_synth_summary, normalize_ids, format_response_for_ui
from src.config.settings import settings


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/summary", tags=["search"])
@router.post("/capa_synthesizer")
async def capa_synthesizer(
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

            # sv (SEARCH_TABLE) only carries description/root_cause_summary/vectors —
            # category, location, and capa_number live on the details table and are
            # only available when it's joined in.
            details_join = ""
            details_select = ""
            if settings.SEARCH_DETAILS_TABLE:
                details_join = (
                    f'LEFT JOIN "{settings.SEARCH_DETAILS_TABLE}" d '
                    f'ON sv."{settings.COLUMN_ID}" = d."{settings.COLUMN_ID}" '
                    f'AND sv."{settings.JOIN_SECONDARY_KEY}" = d."{settings.JOIN_SECONDARY_KEY}"'
                )
                details_select = (
                    f', d."{settings.COLUMN_CATEGORY}" AS "{settings.COLUMN_CATEGORY}"'
                    f', d."{settings.COLUMN_LOCATION}" AS "{settings.COLUMN_LOCATION}"'
                    f', d."{settings.COLUMN_CAPA_NUMBER}" AS "{settings.COLUMN_CAPA_NUMBER}"'
                )

            query = f"""
            SELECT
                sv.*
                {details_select},
                s."{settings.SUMMARY_COL_EVENT_DESCRIPTION}"   AS "{settings.SUMMARY_COL_EVENT_DESCRIPTION}",
                s."{settings.SUMMARY_COL_ROOT_CAUSE}"          AS "{settings.SUMMARY_COL_ROOT_CAUSE}",
                s."{settings.SUMMARY_COL_CAPA}"                AS "{settings.SUMMARY_COL_CAPA}",
                s."{settings.SUMMARY_COL_CAPA_DATE}" AS "{settings.SUMMARY_COL_CAPA_DATE}"
            FROM "{settings.SEARCH_TABLE}" sv
            {details_join}
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
                # `or ""` also covers a present-but-NULL column (e.g. a LEFT
                # JOIN row with no match) — .get()'s default only fires when
                # the key is absent entirely.
                return row_lower.get(col_name.lower()) or ""
            event_records.append(
                CAPAEvent(
                    deviation_id=ci_get(settings.COLUMN_ID),
                    description=ci_get(settings.SUMMARY_COL_EVENT_DESCRIPTION),
                    root_cause_summary=ci_get(settings.SUMMARY_COL_ROOT_CAUSE),
                    root_cause_category=ci_get(settings.COLUMN_CATEGORY),
                    capa_number=ci_get(settings.COLUMN_CAPA_NUMBER),
                    immediate_actions=ci_get(settings.COLUMN_IMMEDIATE_ACTIONS),
                    corrective_actions=ci_get(settings.COLUMN_CORRECTIVE_ACTIONS),
                    preventive_actions=ci_get(settings.COLUMN_PREVENTIVE_ACTIONS),
                    site=ci_get(settings.COLUMN_LOCATION)
                )
            )
    except Exception as exc:
        logger.exception("Failed to normalize DB rows into RCSEvent records")
        raise HTTPException(status_code=500, detail="Data transformation error") from exc

    try:
        logger.info(f"input has {len(event_records)} records")
        result = await get_synth_summary(records=event_records, synth_type="capa")
        final_response = format_response_for_ui(synth_type=SynthType.CAPA,response=result)
        return final_response
    except Exception as exc:
        logger.exception("capa summary synthesis generation failed")
        raise HTTPException(status_code=500, detail="CAPA summary synthesis failed") from exc


