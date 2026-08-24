"""Backfill Problem Statement / Evidence Collection / Interview Questionnaire /
RCI Plan Creation for investigations whose Trackwise module (dim_event.module,
via module_stage.stage_for) already implies those steps are done, but this
app never generated them — e.g. investigations that reached "Interview
Questionnaire" or later natively in Trackwise before this tool existed, so
they have no row yet in investigation_problem_statements /
investigation_evidence_items / investigation_questionnaire_items /
investigation_rci_sections.

Calls the exact same functions the real POST .../generate endpoints use
(ds_client.ds_post + field_mapping.build_trackwise_fields + the
generated_content_queries persist functions) directly, rather than going
through the backend's own HTTP API — so this runs standalone; only the
Postgres DB and the InvestigationAi_DS service need to be reachable, the
backend/frontend dev servers do NOT need to be running.

Each investigation's 4 steps are independent (none of them actually reads
another step's persisted output — they're all built from the same STAR-
schema row via build_trackwise_fields), so a failure on one step (e.g. a
required Trackwise field is genuinely blank for that investigation — the
same "missing required field" a real user would hit generating by hand)
just skips that step and moves on; it never blocks the other 3 steps or
other investigations.

Usage — run separately from the app (not part of any request path):
    cd backend
    uv run python -m backend.scripts.pre_generate_content              # do it for real
    uv run python -m backend.scripts.pre_generate_content --dry-run    # report only, no writes
    uv run python -m backend.scripts.pre_generate_content --limit 20   # first 20 investigations only
    uv run python -m backend.scripts.pre_generate_content --concurrency 5
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
# httpx logs "HTTP Request: POST ... 200 OK" at INFO for every call by
# default — that's exactly the kind of scrolling noise the progress bar
# below is replacing, so it's quieted here rather than left to clutter it.
logging.getLogger("httpx").setLevel(logging.WARNING)


class _Progress:
    """Single updating terminal line instead of one log line per step — per
    the user (2026-07-31), so a run over hundreds of investigations doesn't
    scroll the terminal. Permanent output (failures, the final summary)
    calls .clear() first so it lands on a clean line instead of mangling
    the in-progress one; the next .update() call redraws the bar after."""

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
            # Not an interactive terminal (e.g. piped to a file/CI log) —
            # \r would just be invisible junk, so fall back to one line per
            # update instead of pretending to overwrite anything.
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

# Same de-dup pattern as action_center_queries.py's open-investigations query
# (a deviation_id can legitimately have >1 fact_qms_event row — take the most
# recently updated one as representative). Scoped to currently-open
# investigations only (closed_on IS NULL — same column/convention
# action_center_queries.py uses as authoritative for "open"; date_closed is a
# separate column that can be set on rows still genuinely open, see that
# file's own header comment) — per the user (2026-08-04), this backfill
# should only cover open investigations, not the full all-time history.
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
    e.root_cause_broad_category, e.root_cause_category, e.root_cause_sub_category
FROM fact_qms_event f
JOIN dim_event e ON e.deviation_id = f.deviation_id
LEFT JOIN dim_event_classification ec ON ec.event_classification_key = f.event_classification_key
LEFT JOIN dim_product p ON p.product_key = f.product_key
LEFT JOIN dim_equipment eq ON eq.equipment_key = f.equipment_key
LEFT JOIN dim_batch b ON b.batch_key = f.batch_key
WHERE f.closed_on IS NULL
ORDER BY f.deviation_id, f.pg_updated_at_timestamp DESC NULLS LAST
"""

# stage_for()'s return value is the "modules done" count (see
# module_stage.py's MODULE_LABELS/next_module_label) — Problem Statement is
# done once stage >= 1, Evidence Collection >= 2, Interview Questionnaire
# >= 3, RCI Plan Creation >= 4. STATUS_TO_STAGE only has entries starting at
# stage 3 ("interview questionnaire"), so in practice this only ever fires
# for investigations already at "interview questionnaire" module or later.
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


# Each step is split into a DS "fetch" phase and a DB "persist" phase (rather
# than one function doing both) so _process_investigation can re-check _needs()
# in between — the DS call is the slow part (seconds, per our own test run),
# and that's the real window in which a live user (this app's DB is used by
# the running frontend/backend at the same time — see project memory: don't
# manage dev servers) could generate the same step by hand. Without the
# re-check, this script would silently clobber that fresher, real generation
# with its own redundant one once its slower DS call finally came back.


async def _fetch_problem_statement(row, event_type: str) -> ProblemStatementGenerateResponse:
    # Market Complaint gets the extended field set only for problem-statement
    # (see routers/problem_statement.py's GET handler).
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
    # Deviation gets the extended field set only for rci-plan (see
    # routers/rci_plan.py's GET handler).
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
                "six_m_bucket": section.six_m_bucket,
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
    """Every failure records exactly what a human needs to go look at: which
    investigation, which of the 4 steps, and at what point it gave up — per
    the user (2026-07-31), so failures are never just a scroll-back-through-
    the-log exercise. progress.clear() first so the traceback lands on a
    clean line instead of mangling the in-progress bar."""
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

            # Re-check right before writing (see the comment above _fetch_*)
            # — skip the write entirely if this step got generated some
            # other way while we were waiting on DS.
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
