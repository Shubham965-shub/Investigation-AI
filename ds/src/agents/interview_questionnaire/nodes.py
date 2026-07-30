"""
Interview-questionnaire-specific LangGraph nodes.
parse_input / fetch_archetypes / map_to_archetype live in src.agents.shared.nodes.
"""

import asyncpg
import json
import logging


from src.agents.interview_questionnaire.state import InterviewQuestionCollectionState
from src.config.settings import settings
from src.utils.deps import get_llm_client, get_prompt_registry

logger = logging.getLogger(__name__)


async def fetch_questions(
    state: InterviewQuestionCollectionState,
) -> InterviewQuestionCollectionState:
    """Fetch interview questions for the mapped archetype."""
    if state.mapped_archetype.get("id") is None:
        state.question_list = []
        return state

    # settings.DATABASE_URL (not a raw f-string) — DB_PASSWORD contains
    # characters (#, ,) that are URL-structural if not percent-encoded;
    # unencoded, asyncpg fails to parse the DSN at all, silently caught by
    # the except below and turning every call into "no questions found".
    db_url = settings.DATABASE_URL
    try:
        conn = await asyncpg.connect(db_url)
        try:
            rows = await conn.fetch(
                "SELECT id, description FROM interview_questionnaire WHERE archetype_id = $1 ORDER BY id",
                state.mapped_archetype["id"],
            )
            state.question_list = [{"id": r["id"], "description": r["description"]} for r in rows]
            logger.info(
                f"Fetched {len(state.question_list)} questions for archetype '{state.mapped_archetype['name']}'"
            )
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"Error fetching questions: {e}")
        state.question_list = []
    return state


async def rephrase_questions(
    state: InterviewQuestionCollectionState,
) -> InterviewQuestionCollectionState:
    """Contextualise questions using trackwise fields without altering their essence."""
    if not state.question_list:
        state.rephrased_questions = []
        return state

    try:
        llm = await get_llm_client()
    except Exception:
        from src.llm.client import LLMClient
        llm = LLMClient()

    registry = get_prompt_registry()
    questions_str = "\n".join(f"{i+1}. {q['description']}" for i, q in enumerate(state.question_list))
    tw_fields_str = "\n".join(f"- {k}: {v}" for k, v in state.trackwise_fields.items())
    prompt = registry.get("interview_questionnaire/rephrase_questions").format(
        archetype_name=state.mapped_archetype["name"],
        event_type=state.event_type,
        tw_fields_str=tw_fields_str,
        questions_str=questions_str,
    )

    result = await llm.chat(prompt)
    try:
        rephrased = json.loads(result.strip())
        if not isinstance(rephrased, list):
            raise ValueError("Expected a JSON array")
    except Exception:
        logger.error(f"Rephrase JSON parse failed, using originals. LLM output: {result}")
        rephrased = state.question_list

    state.rephrased_questions = [
        {
            "id": orig.get("id"),
            "description": (
                reph.get("description", orig.get("description"))
                if isinstance(reph, dict)
                else orig.get("description")
            ),
            "is_new": False,
        }
        for orig, reph in zip(state.question_list, rephrased)
    ]
    logger.info(f"Rephrased {len(state.rephrased_questions)} questions")
    return state


async def infer_questions_from_historical_data(
    state: InterviewQuestionCollectionState,
) -> InterviewQuestionCollectionState:
    """Infer interview questions by mining rich investigation fields from historical incidents."""
    llm = await get_llm_client()

    def _truncate(text: str | None, limit: int = 600) -> str:
        if not text:
            return ""
        text = text.strip()
        return text[:limit] + "…" if len(text) > limit else text

    top_hits = (state.search_results or [])[:5]
    incident_blocks: list[str] = []
    for i, h in enumerate(top_hits, 1):
        parts = [f"Incident {i}: {h.get('title', 'Untitled')}"]
        if inv := _truncate(h.get("investigation_summary")):
            parts.append(f"  Investigation: {inv}")
        if imm := _truncate(h.get("immediate_action")):
            parts.append(f"  Immediate action: {imm}")
        if act := _truncate(h.get("actions_taken")):
            parts.append(f"  Actions taken: {act}")
        if rc := _truncate(h.get("root_cause_summary")):
            parts.append(f"  Root cause: {rc}")
        incident_blocks.append("\n".join(parts))

    history_text = "\n\n".join(incident_blocks) if incident_blocks else "No historical incidents found."

    registry = get_prompt_registry()
    prompt = registry.get("interview_questionnaire/infer_questions").format(
        failure_type=state.failure_type,
        event_type=state.event_type,
        history_text=history_text,
    )

    try:
        result = await llm.chat(prompt)
        items = json.loads(result.strip())
        if not isinstance(items, list):
            raise ValueError("Expected a JSON array")
    except Exception:
        logger.exception("Failed to infer questions from historical data")
        items = []

    cleaned: list[str] = []
    for item in items:
        if isinstance(item, str) and item.strip():
            cleaned.append(item.strip())
            if len(cleaned) >= 10:
                break

    state.new_questions = cleaned
    logger.info(f"Inferred {len(cleaned)} questions from historical data")
    return state


async def format_result(
    state: InterviewQuestionCollectionState,
) -> InterviewQuestionCollectionState:
    """Assemble the final response from rephrased + inferred questions."""
    all_questions = (
        state.rephrased_questions.copy() if state.rephrased_questions else state.question_list.copy()
    )
    for new_q in state.new_questions:
        all_questions.append({"description": new_q, "is_new": True})

    state.final_result = {
        "event_type": state.event_type,
        "failure_type": state.failure_type,
        "archetype": {
            "id": state.mapped_archetype.get("id"),
            "name": state.mapped_archetype.get("name"),
            "is_new": state.is_new_archetype,
            "confidence_score": state.confidence_score,
            "reasoning": state.reasoning,
        },
        "questions": [
            {"description": q.get("description") or q, "is_new": q.get("is_new", False)}
            for q in all_questions
        ],
        "total_questions_count": len(all_questions),
    }
    logger.info(
        f"Final result: {len(all_questions)} questions for archetype '{state.mapped_archetype['name']}'"
    )
    return state
