"""
Evidence-collection-specific LangGraph nodes.
parse_input / fetch_archetypes / map_to_archetype live in src.agents.shared.nodes.
"""

import asyncpg
import json
import logging

from src.agents.evidence_collection.state import EvidenceCollectionState
from src.config.settings import settings
from src.utils.deps import get_llm_client, get_prompt_registry

logger = logging.getLogger(__name__)


async def fetch_evidence(state: EvidenceCollectionState) -> EvidenceCollectionState:
    """Fetch evidence items for the mapped archetype."""
    if state.mapped_archetype.get("id") is None:
        state.evidence_list = []
        return state

    # settings.DATABASE_URL (not a raw f-string) — DB_PASSWORD contains
    # characters (#, ,) that are URL-structural if not percent-encoded;
    # unencoded, asyncpg fails to parse the DSN at all, silently caught by
    # the except below and turning every call into "no evidence found".
    db_url = settings.DATABASE_URL
    try:
        conn = await asyncpg.connect(db_url)
        try:
            rows = await conn.fetch(
                "SELECT id, description FROM evidence WHERE archetype_id = $1 ORDER BY id",
                state.mapped_archetype["id"],
            )
            state.evidence_list = [{"id": r["id"], "description": r["description"]} for r in rows]
            logger.info(f"Fetched {len(state.evidence_list)} evidence items")
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"Error fetching evidence: {e}")
        state.evidence_list = []
    return state


async def rephrase_evidence(state: EvidenceCollectionState) -> EvidenceCollectionState:
    """Contextualise evidence items using trackwise fields without altering their essence."""
    if not state.evidence_list:
        state.rephrased_evidence = []
        return state

    try:
        llm = await get_llm_client()
    except Exception:
        from src.llm.client import LLMClient
        llm = LLMClient()

    registry = get_prompt_registry()
    evidence_str = "\n".join(f"{i+1}. {e['description']}" for i, e in enumerate(state.evidence_list))
    tw_fields_str = "\n".join(f"- {k}: {v}" for k, v in state.trackwise_fields.items())
    prompt = registry.get("evidence_collection/rephrase_evidence").format(
        archetype_name=state.mapped_archetype["name"],
        event_type=state.event_type,
        tw_fields_str=tw_fields_str,
        evidence_str=evidence_str,
    )

    result = await llm.chat(prompt)
    try:
        rephrased = json.loads(result.strip())
        if not isinstance(rephrased, list):
            raise ValueError("Expected a JSON array")
    except Exception:
        logger.error(f"Rephrase JSON parse failed, using originals. LLM output: {result}")
        rephrased = state.evidence_list

    state.rephrased_evidence = [
        {
            "id": orig.get("id"),
            "description": (
                reph.get("description", orig.get("description"))
                if isinstance(reph, dict)
                else orig.get("description")
            ),
            "is_new": False,
        }
        for orig, reph in zip(state.evidence_list, rephrased)
    ]
    logger.info(f"Rephrased {len(state.rephrased_evidence)} evidence items")
    return state


async def check_exhaustiveness(state: EvidenceCollectionState) -> EvidenceCollectionState:
    """LLM check: is the current evidence list comprehensive?"""
    if state.is_new_archetype or not state.evidence_list:
        state.is_exhaustive = False
        return state

    try:
        llm = await get_llm_client()
    except Exception:
        from src.llm.client import LLMClient
        llm = LLMClient()

    registry = get_prompt_registry()
    evidence_str = "\n".join(f"- {e['description']}" for e in state.evidence_list)
    prompt = registry.get("evidence_collection/check_exhaustiveness").format(
        archetype_name=state.mapped_archetype["name"],
        event_type=state.event_type,
        evidence_str=evidence_str,
    )

    result = await llm.chat(prompt)
    try:
        check = json.loads(result.strip())
        state.is_exhaustive = bool(check.get("is_exhaustive", False))
    except json.JSONDecodeError:
        logger.error(f"Exhaustiveness check JSON parse failed: {result}")
        state.is_exhaustive = False

    logger.info(f"Exhaustiveness check: {state.is_exhaustive}")
    return state


async def generate_evidence(state: EvidenceCollectionState) -> EvidenceCollectionState:
    """Generate additional evidence items via LLM when the existing list is not exhaustive."""
    try:
        llm = await get_llm_client()
    except Exception:
        from src.llm.client import LLMClient
        llm = LLMClient()

    registry = get_prompt_registry()
    existing = (
        "\n".join(f"- {e['description']}" for e in state.evidence_list)
        if state.evidence_list
        else "None"
    )
    prompt = registry.get("evidence_collection/generate_evidence").format(
        archetype_name=state.mapped_archetype["name"],
        event_type=state.event_type,
        trackwise_fields_json=json.dumps(state.trackwise_fields, indent=2),
        existing_evidence=existing,
    )

    result = await llm.chat(prompt)
    try:
        items = json.loads(result.strip())
        state.new_evidence = items if isinstance(items, list) else []
    except json.JSONDecodeError:
        logger.error(f"generate_evidence JSON parse failed: {result}")
        state.new_evidence = []

    logger.info(f"Generated {len(state.new_evidence)} new evidence items")
    return state


async def format_result(state: EvidenceCollectionState) -> EvidenceCollectionState:
    """Assemble the final response from rephrased + generated evidence."""
    all_evidence = (
        state.rephrased_evidence.copy() if state.rephrased_evidence else state.evidence_list.copy()
    )
    for new_ev in state.new_evidence:
        all_evidence.append({"description": new_ev, "is_new": True})

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
        "evidence": [
            {"description": ev.get("description") or ev, "is_new": ev.get("is_new", False)}
            for ev in all_evidence
        ],
        "total_evidence_count": len(all_evidence),
    }
    logger.info(
        f"Final result: {len(all_evidence)} evidence items for archetype '{state.mapped_archetype['name']}'"
    )
    return state


async def infer_evidence_from_historical_data(state: EvidenceCollectionState) -> EvidenceCollectionState:
    """Infer evidence items by mining rich investigation fields from historical incidents."""
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
    tw_fields_str = "\n".join(f"- {k}: {v}" for k, v in state.trackwise_fields.items())

    registry = get_prompt_registry()
    prompt = registry.get("evidence_collection/infer_evidence").format(
        event_type=state.event_type,
        trackwise_fields=tw_fields_str,
        history_text=history_text,
    )

    try:
        result = await llm.chat(prompt)
        print(f"LLM output for historical inference: {result}")
        items = json.loads(result.strip())
        if not isinstance(items, list):
            raise ValueError("Expected a JSON array")
    except Exception:
        logger.exception("Failed to infer evidence from historical data")
        items = []

    cleaned: list[str] = []
    for item in items:
        if isinstance(item, str) and item.strip():
            cleaned.append(item.strip())
            if len(cleaned) >= 10:
                break

    state.new_evidence = cleaned
    state.is_exhaustive = bool(cleaned)
    logger.info(f"Inferred {len(cleaned)} evidence items from historical data")
    return state
