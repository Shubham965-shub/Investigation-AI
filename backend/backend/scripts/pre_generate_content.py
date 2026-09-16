"""Backfill Problem Statement/Evidence/Questionnaire/RCI Plan for investigations whose Trackwise stage implies they're done but were never generated here.

Usage: cd backend && uv run python -m backend.scripts.pre_generate_content [--dry-run] [--limit N] [--concurrency N]
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from backend.clients import db_client, ds_client
from backend.db.field_mapping import build_trackwise_fields, resolved_event_type
from backend.db.generated_content_queries import (
    fetch_evidence_items,
    fetch_problem_statement,
    fetch_questionnaire_items,
    fetch_rci_sections,
    replace_evidence_items,
    replace_questionnaire_items,
    replace_rci_sections,
    save_problem_statement,
)
from backend.db.module_stage import stage_for
from backend.schemas.evidence import EvidenceCollectionResponse
from backend.schemas.problem_statement import ProblemStatementGenerateResponse
from backend.schemas.questionnaire import QuestionnaireGenerateResponse
from backend.schemas.rci_plan import RciPlanGenerateResponse

logging.basicConfig(format="%(asctime)s | %(levelname)-7s | %(message)s", level=logging.INFO)
logger = logging.getLogger("pre_generate_content")
# Quiet httpx's per-request INFO logs so they don't clutter the progress bar below.
logging.getLogger("httpx").setLevel(logging.WARNING)


class _Progress:
    """Single updating terminal line instead of one log line per step; permanent output calls .clear() first to avoid mangling it."""

    def __init__(self, total: int) -> None:
        self.total = total
        self.done = 0
        self._line_len = 0
        self._is_tty = sys.stdout.isatty()

    def clear(self) -> None:
        if self._is_tty and self._line_len:
            sys.stdout.write("\r" + " " * self._line_len + "\r")
            sys.stdout.flush()
        self._line_len = 0

    def update(self, deviation_id: int, step: str, note: str = "") -> None:
        line = f"[{self.done}/{self.total}] deviation_id={deviation_id} -> {step}" + (f" ({note})" if note else "")
        if not self._is_tty:
            # Not a terminal (e.g. piped to a file) — \r would be invisible junk, so print one line per update instead.
            print(line)
            return
        self.clear()
        sys.stdout.write(line)
        sys.stdout.flush()
        self._line_len = len(line)

    def advance(self) -> None:
        self.done += 1

    def finish(self) -> None:
        self.clear()

# Dedupes to the most recently updated fact_qms_event row per deviation_id; scoped to open investigations only (closed_on IS NULL).
_ALL_INVESTIGATIONS_QUERY = """
SELECT DISTINCT ON (f.deviation_id)
    f.deviation_id,
    ec.qe_type,
    e.module AS status,
    e.failure_type, e.title, e.description, e.deviation_to, e.deviation_number,
    f.date_opened, e.observation_date, e.observation_time, e.failure_duration,
    e.immediate_cause_known, e.cause_detail, e.immediate_actions,
    e.impact_on_deviation_batches, e.impact_details, e.proposal_for_resolution,
    e.market, e.related_market, e.laboratory_details, e.name_of_test,
    e.sample_number, e.specification_number, e.stability_condition,
    e.stability_protocol_number, e.stability_time_point, e.stp_number,
    e.labelled_storage_conditions, e.complaint_number, e.complainant_name,
    e.complainant_country, e.complaint_received_by, e.complaint_reported_by,
    e.customer, e.date_complaint_received, e.reference_complaint_number,
    e.sfg_code, e.product_type, e.dosage_form, e.product_manufacturing_info,
    b.batch_no, e.related_customer, e.originator, e.analyst_name,
    e.owner_name, e.observed_by, p.name_of_material,
    eq.instrument_equipment, eq.instrument_equipment_id,
    e.root_cause_broad_category, e.root_cause_category, e.root_cause_sub_category,
    d.department
FROM fact_qms_event f
JOIN dim_event e ON e.deviation_id = f.deviation_id
LEFT JOIN dim_event_classification ec ON ec.event_classification_key = f.event_classification_key
LEFT JOIN dim_product p ON p.product_key = f.product_key
LEFT JOIN dim_equipment eq ON eq.equipment_key = f.equipment_key
LEFT JOIN dim_batch b ON b.batch_key = f.batch_key
LEFT JOIN dim_department d ON d.department_key = f.department_key
WHERE f.closed_on IS NULL
ORDER BY f.deviation_id, f.pg_updated_at_timestamp DESC NULLS LAST
"""

# stage_for()'s return value is the "modules done" count: PS >= 1, Evidence >= 2, Questionnaire >= 3, RCI Plan >= 4.
_STAGE_REQUIRED = {"problem_statement": 1, "evidence": 2, "questionnaire": 3, "rci_plan": 4}
_STEPS = ("problem_statement", "evidence", "questionnaire", "rci_plan")


async def _needs(step: str, deviation_id: int, stage: int) -> bool:
    if stage < _STAGE_REQUIRED[step]:
        return False
    if step == "problem_statement":
        return await fetch_problem_statement(deviation_id) is None
    if step == "evidence":
        return not await fetch_evidence_items(deviation_id)
    if step == "questionnaire":
        return not await fetch_questionnaire_items(deviation_id)
    return not await fetch_rci_sections(deviation_id)  # rci_plan


# Split into fetch/persist phases so _process_investigation can re-check _needs() between them — without it, a slow DS call could clobber a fresher real generation made by a live user in the meantime.


async def _fetch_problem_statement(row, event_type: str) -> ProblemStatementGenerateResponse:
    # Market Complaint gets the extended field set only for problem-statement.
    fields = build_trackwise_fields(row, row["qe_type"], extended=event_type == "Market Complaint")
    data = await ds_client.ds_post("/ps/v2/generate", json={"event_type": event_type, "trackwise_fields": fields})
    return ProblemStatementGenerateResponse(**data)


async def _persist_problem_statement(deviation_id: int, response: ProblemStatementGenerateResponse) -> None:
    await save_problem_statement(deviation_id, response.problem_statement)


async def _fetch_evidence(row, event_type: str) -> EvidenceCollectionResponse:
    fields = build_trackwise_fields(row, row["qe_type"], extended=False)
    data = await ds_client.ds_post("/evidence/collect", json={"event_type": event_type, "trackwise_fields": fields})
    return EvidenceCollectionResponse(**data)


async def _persist_evidence(deviation_id: int, response: EvidenceCollectionResponse) -> None:
    await replace_evidence_items(
        deviation_id, [{"description": e.description, "is_checked": True} for e in response.evidence]
    )


async def _fetch_questionnaire(row, event_type: str) -> QuestionnaireGenerateResponse:
    fields = build_trackwise_fields(row, row["qe_type"], extended=False)
    data = await ds_client.ds_post("/interview/questionnaire", json={"event_type": event_type, "trackwise_fields": fields})
    return QuestionnaireGenerateResponse(**data)


async def _persist_questionnaire(deviation_id: int, response: QuestionnaireGenerateResponse) -> None:
    await replace_questionnaire_items(
        deviation_id, [{"description": q.description, "is_checked": True} for q in response.questions]
    )


async def _fetch_rci_plan(row, event_type: str) -> RciPlanGenerateResponse:
    # Deviation gets the extended field set only for rci-plan.
    fields = build_trackwise_fields(row, row["qe_type"], extended=event_type == "Deviation")
    data = await ds_client.ds_post("/rci/plan", json={"event_type": event_type, "trackwise_fields": fields})
    return RciPlanGenerateResponse(**data)


async def _persist_rci_plan(deviation_id: int, response: RciPlanGenerateResponse) -> None:
    await replace_rci_sections(
        deviation_id,
        [
            {
                "title": section.title,
                "correlation": section.correlation,
                "due_date": None,
                "assignee": None,
                "tasks": [{"description": task.description} for task in section.tasks],
            }
            for section in response.sections
        ],
    )


_FETCHERS = {
    "problem_statement": _fetch_problem_statement,
    "evidence": _fetch_evidence,
    "questionnaire": _fetch_questionnaire,
    "rci_plan": _fetch_rci_plan,
}
_PERSISTERS = {
    "problem_statement": _persist_problem_statement,
    "evidence": _persist_evidence,
    "questionnaire": _persist_questionnaire,
    "rci_plan": _persist_rci_plan,
}


def _record_failure(progress: "_Progress", failures: list, deviation_id: int, step: str, stage: str, exc: Exception) -> None:
    """Records which investigation/step/stage failed; progress.clear() first so the traceback doesn't mangle the in-progress bar."""
    progress.clear()
    logger.exception("deviation_id=%s stopped at step=%s (%s)", deviation_id, step, stage)
    failures.append({"deviation_id": deviation_id, "step": step, "stage": stage, "error": str(exc)})


async def _process_investigation(
    row, semaphore: asyncio.Semaphore, dry_run: bool, stats: dict, failures: list, progress: "_Progress"
) -> None:
    deviation_id = row["deviation_id"]
    stage = stage_for(row["status"])
    event_type = resolved_event_type(row["qe_type"])
    if event_type is None:
        progress.advance()
        return  # unmapped/unknown qe_type — nothing to generate against

    async with semaphore:
        for step in _STEPS:
            try:
                if not await _needs(step, deviation_id, stage):
                    continue
            except Exception as exc:
                _record_failure(progress, failures, deviation_id, step, "checking existing data", exc)
                continue

            if dry_run:
                progress.update(deviation_id, step, "would generate")
                stats[step] += 1
                continue

            progress.update(deviation_id, step, "generating")
            try:
                response = await _FETCHERS[step](row, event_type)
            except Exception as exc:
                stats[f"{step}_failed"] += 1
                _record_failure(progress, failures, deviation_id, step, "generating (DS call)", exc)
                continue

            # Re-check right before writing — skip if this step got generated some other way while waiting on DS.
            try:
                if not await _needs(step, deviation_id, stage):
                    continue
            except Exception as exc:
                _record_failure(progress, failures, deviation_id, step, "re-checking before write", exc)
                continue

            progress.update(deviation_id, step, "saving")
            try:
                await _PERSISTERS[step](deviation_id, response)
                stats[step] += 1
            except Exception as exc:
                stats[f"{step}_failed"] += 1
                _record_failure(progress, failures, deviation_id, step, "persisting to the DB", exc)

    progress.advance()
    progress.update(deviation_id, "done", "")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="Report what would be generated without calling DS or writing to the DB")
    parser.add_argument("--concurrency", type=int, default=15, help="Investigations processed in parallel (default 3)")
    parser.add_argument("--limit", type=int, default=None, help="Only consider the first N investigations (for testing)")
    args = parser.parse_args()

    await db_client.create_pool()
    ds_client.create_client()
    try:
        pool = db_client.get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(_ALL_INVESTIGATIONS_QUERY)
        if args.limit:
            rows = rows[: args.limit]

        logger.info("Checking %d investigations (concurrency=%d, dry_run=%s)...", len(rows), args.concurrency, args.dry_run)
        stats = {k: 0 for step in _STEPS for k in (step, f"{step}_failed")}
        failures: list = []
        progress = _Progress(len(rows))
        semaphore = asyncio.Semaphore(args.concurrency)
        await asyncio.gather(
            *(_process_investigation(row, semaphore, args.dry_run, stats, failures, progress) for row in rows)
        )
        progress.finish()

        logger.info("Done. %s", stats)
        if failures:
            logger.warning("=== %d failure(s) — investigation/step/where it stopped ===", len(failures))
            for f in failures:
                logger.warning("  deviation_id=%s | step=%s | stopped while %s | %s", f["deviation_id"], f["step"], f["stage"], f["error"])
        else:
            logger.info("No failures.")
    finally:
        await ds_client.close_client()
        await db_client.close_pool()


if __name__ == "__main__":
    asyncio.run(main())
