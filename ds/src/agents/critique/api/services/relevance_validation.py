from __future__ import annotations

from fastapi import HTTPException, status
from pydantic import BaseModel

from src.llm.client import LLMClient

_MAX_DOCUMENT_CHARS = 12000

_RELEVANCE_PROMPT = """You are a pharmaceutical QA expert gatekeeping document uploads before they are critiqued.

Given problem statement:
{problem_statement}

Event type: {event_type}
{task_context_block}
Uploaded document (labeled "{document_label}"), content below:
---
{document_text}
---

Decide whether this document is a genuine, on-topic {document_label} for the investigation described by
the problem statement above{task_context_clause}. Mark is_relevant = false if any of the following is true:
- The document is not a pharmaceutical investigation document at all (e.g. a resume, invoice, unrelated
  business document, or other content with no connection to a deviation/OOS/OOT/complaint investigation).
- The document is random/gibberish text, keyboard mashing, or otherwise has no discernible meaning.
- The document's content (findings, tasks, root cause, or CAPA) clearly pertains to a different problem,
  event, product, or investigation than the one described in the problem statement — i.e. it looks like the
  wrong file was uploaded.{task_mismatch_bullet}

Do not mark is_relevant = false merely because the document is incomplete, brief, or imperfectly written —
only reject genuine mismatches or irrelevant/meaningless content.

Return JSON with:
  is_relevant: true if the document is an on-topic {document_label} for this problem statement{task_context_suffix}, false otherwise.
  reason: one short sentence explaining the verdict — if is_relevant is false, state concretely what about the
    document does not match the problem statement{task_context_suffix2}.

Return ONLY valid JSON. No markdown fences."""


class DocumentRelevanceResult(BaseModel):
    is_relevant: bool
    reason: str


async def validate_document_relevance(
    llm: LLMClient,
    *,
    problem_statement: str,
    event_type: str,
    document_text: str,
    document_label: str,
    task_context: str = "",
) -> None:
    """Raise HTTPException(422) if the uploaded document doesn't genuinely pertain to
    the given problem statement/event, or isn't a real investigation document at all.

    When `task_context` is given (task-critique flow: one upload per RCI-plan task,
    e.g. "Analyst Verification" or "Instrument Calibration Check"), also verify the
    document's content actually addresses that specific task — catches the wrong
    task's write-up being uploaded to the wrong section, not just a wrong investigation
    entirely."""
    task_context_block = (
        f"\nThis upload is specifically meant to report on the following investigation task:\n{task_context}\n"
        if task_context else "\n"
    )
    task_context_clause = " and the specific investigation task below" if task_context else ""
    task_mismatch_bullet = (
        "\n- The document's content does not actually address the specific investigation task above — e.g. "
        "it reports on a different task area entirely (an analyst-competency write-up uploaded where an "
        "instrument-qualification report was expected, or vice versa)."
        if task_context else ""
    )
    task_context_suffix = " and the given investigation task" if task_context else ""
    task_context_suffix2 = " or the investigation task" if task_context else ""

    prompt = _RELEVANCE_PROMPT.format(
        problem_statement=problem_statement,
        event_type=event_type or "Not specified",
        document_label=document_label,
        document_text=document_text[:_MAX_DOCUMENT_CHARS],
        task_context_block=task_context_block,
        task_context_clause=task_context_clause,
        task_mismatch_bullet=task_mismatch_bullet,
        task_context_suffix=task_context_suffix,
        task_context_suffix2=task_context_suffix2,
    )
    result: DocumentRelevanceResult = await llm.get_structured_response(
        user_prompt=prompt,
        structure=DocumentRelevanceResult,
    )
    if not result.is_relevant:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"The uploaded {document_label} does not appear to be relevant to the "
                f"provided problem statement{' or investigation task' if task_context else ''}. "
                f"{result.reason}".strip()
            ),
        )
