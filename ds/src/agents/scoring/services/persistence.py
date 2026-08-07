"""
Persist scoring results (the audit trail / "why") to Postgres.

Two tables in the public schema:
  • investigation_ai_report_score            — one row per scoring run (summary + full JSONB snapshot)
  • investigation_ai_report_score_checkpoint — one row per checkpoint (verdict, marks, rationale, evidence)

The per-checkpoint rows make the reasoning queryable (e.g. "show every checkpoint
scored 0 and why"). Persistence is best-effort — failures here never break scoring.
Tables are created lazily (CREATE TABLE IF NOT EXISTS) so no migration tool is required.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Optional

import asyncpg

from src.agents.scoring.api.schemas import ScoringReportResponse

logger = logging.getLogger(__name__)

RUN_TABLE = "public.investigation_ai_report_score"
CHECKPOINT_TABLE = "public.investigation_ai_report_score_checkpoint"

DDL = f"""
CREATE TABLE IF NOT EXISTS {RUN_TABLE} (
    id                      uuid PRIMARY KEY,
    created_at              timestamptz NOT NULL DEFAULT now(),
    filename                text,
    event_type              text,
    detected_sections       text[],
    score                   int,
    overall_percentage      double precision,
    overall_marks           double precision,
    overall_max             double precision,
    task_report_percentage  double precision,
    iq_percentage           double precision,
    breakdown               jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS {CHECKPOINT_TABLE} (
    id              bigserial PRIMARY KEY,
    run_id          uuid NOT NULL REFERENCES {RUN_TABLE}(id) ON DELETE CASCADE,
    section         text NOT NULL,
    checkpoint_id   text NOT NULL,
    sub_criteria    text,
    checkpoint_text text,
    max_marks       numeric,
    verdict         text,
    marks_awarded   numeric,
    applicable      boolean,
    rationale       text,
    evidence_quote  text
);

CREATE INDEX IF NOT EXISTS ix_report_score_checkpoint_run
    ON {CHECKPOINT_TABLE}(run_id);
"""

_INSERT_RUN = f"""
INSERT INTO {RUN_TABLE}
    (id, filename, event_type, detected_sections, score, overall_percentage,
     overall_marks, overall_max, task_report_percentage, iq_percentage, breakdown)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::jsonb);
"""

_INSERT_CHECKPOINT = f"""
INSERT INTO {CHECKPOINT_TABLE}
    (run_id, section, checkpoint_id, sub_criteria, checkpoint_text, max_marks,
     verdict, marks_awarded, applicable, rationale, evidence_quote)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11);
"""


async def persist_score(
    pool: Optional[asyncpg.Pool],
    filename: Optional[str],
    response: ScoringReportResponse,
) -> Optional[str]:
    """Persist a scoring run + its per-checkpoint evidence. Returns the run id, or
    None if there's no pool or the write fails (best-effort)."""
    if pool is None:
        return None

    run_id = str(uuid.uuid4())
    task_pct = response.task_report_execution.percentage if response.task_report_execution else None
    iq_pct = response.iq_score.percentage if response.iq_score else None
    checkpoint_rows = [
        (run_id, section.section, c.id, c.sub_criteria, c.checkpoint_text, c.max_marks,
         c.verdict, c.marks_awarded, c.applicable, c.rationale, c.evidence_quote)
        for section in response.sections.values()
        for c in section.checkpoints
    ]

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(DDL)
                await conn.execute(
                    _INSERT_RUN,
                    run_id, filename, response.event_type, response.detected_sections,
                    response.score, response.overall_percentage, response.overall_marks,
                    response.overall_max, task_pct, iq_pct, json.dumps(response.model_dump()),
                )
                if checkpoint_rows:
                    await conn.executemany(_INSERT_CHECKPOINT, checkpoint_rows)
        logger.info("Persisted scoring run %s (%d checkpoints)", run_id, len(checkpoint_rows))
        return run_id
    except Exception as exc:  # noqa: BLE001 - persistence is best-effort
        logger.warning("Failed to persist report score: %s", exc)
        return None
