"""endpoint for getting event record summaries"""

from __future__ import annotations

import logging

from datetime import date
from dateutil.relativedelta import relativedelta
from fastapi import APIRouter, Depends, HTTPException

from src.utils.deps import get_db_pool
from src.agents.search_agent.api.schemas import (
    CumulativeSummaryRequest,
    EREvent,
    SynthType
)
from src.agents.search_agent.api.services.summary_synthesizer import get_synth_summary, normalize_ids, format_response_for_ui
from src.config.settings import settings


logger = logging.getLogger(__name__)

from datetime import date, datetime

from datetime import date, datetime

def split_by_age(events):
    today = date.today()

    zero_to_six = []
    seven_to_twelve = []

    for event in events:
        raw_date = event.date_opened

        if not raw_date:
            logger.warning("Missing date for deviation_id=%s", event.deviation_id)
            continue

        try:
            # Handle common Postgres formats
            if isinstance(raw_date, str):
                raw_date = raw_date.replace("Z", "")
                opened = datetime.fromisoformat(raw_date.split(" ")[0]).date()
            else:
                opened = raw_date

            months_old = (
                (today.year - opened.year) * 12
                + (today.month - opened.month)
            )

            if 0 <= months_old <= 6:
                zero_to_six.append(event)
            elif 7 <= months_old <= 12:
                seven_to_twelve.append(event)

        except Exception as exc:
            logger.error(
                "Date parse failed: deviation_id=%s, value=%r, error=%s",
                event.deviation_id, raw_date, exc,
            )

    return zero_to_six, seven_to_twelve


router = APIRouter(prefix="/summary", tags=["search"])
@router.post("/er_synthesizer")
async def event_record_synthesizer(
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
                EREvent(
                    deviation_id=ci_get(settings.COLUMN_ID),
                    date_opened=ci_get(settings.COLUMN_DATE_OPENED),
                    description=ci_get(settings.COLUMN_DESCRIPTION),
                    root_cause_category=ci_get(settings.COLUMN_CATEGORY),
                    root_cause_summary=ci_get(settings.SUMMARY_COL_ROOT_CAUSE),
                    site=ci_get(settings.COLUMN_LOCATION)
                )
            )
    except Exception as exc:
        logger.exception("Failed to normalize DB rows into RCSEvent records")
        raise HTTPException(status_code=500, detail="Data transformation error") from exc

    zero_to_six, seven_to_twelve = split_by_age(event_records)
    def attach_age_bucket(records, label: str):
        for r in records:
            setattr(r, "age_bucket", label)
        return records
    
    zero_to_six = attach_age_bucket(zero_to_six, "0–6 months")
    seven_to_twelve = attach_age_bucket(seven_to_twelve, "7–12 months")

    all_event_records = zero_to_six + seven_to_twelve

    logger.info(
        "Events split: 0–6 months=%s, 7–12 months=%s",
        len(zero_to_six),
        len(seven_to_twelve),
    )

    try:
        if not zero_to_six and not seven_to_twelve:
            return []
        logger.info(f"input has {len(event_records)} records")
        result = await get_synth_summary(records=all_event_records, synth_type="event")
        final_response = format_response_for_ui(synth_type=SynthType.EVENT,response=result)
        return final_response
    except Exception as exc:
        logger.exception("event record summary synthesis generation failed")
        raise HTTPException(status_code=500, detail="event record summary synthesis failed") from exc


