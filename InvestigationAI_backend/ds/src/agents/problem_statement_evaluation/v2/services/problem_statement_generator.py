"""
Service to generate structured problem statements from trackwise fields using LLM.
"""

from typing import Dict, Any
import logging
from src.utils.deps import get_llm_client, get_prompt_registry

logger = logging.getLogger(__name__)


def _format_fields_for_prompt(trackwise_fields: Dict[str, Any]) -> str:
    lines = []
    for key, value in trackwise_fields.items():
        if value is None:
            continue
        if isinstance(value, str):
            value = value.strip()
            if value == "":
                continue
        lines.append(f"{key}: {value}")
    return "\n".join(lines)


def _prompt_name_for_event(event_type: str) -> str:
    normalized = (event_type or "").strip().lower()
    if normalized == "deviation":
        return "ps_generation/deviation"
    if normalized == "oos":
        return "ps_generation/oos"
    if normalized == "oot":
        return "ps_generation/oot"
    if normalized in ("market complaint", "marketcomplaint", "complaint", "complaints", "mc"):
        return "ps_generation/market_complaint"
    return "ps_generation/generic"


async def generate_problem_statement(
    event_type: str,
    trackwise_fields: Dict[str, Any],
) -> Dict[str, Any]:
    """Generate a problem statement from Trackwise fields using the active prompt version."""
    try:
        llm = await get_llm_client()
        registry = get_prompt_registry()

        formatted_fields = _format_fields_for_prompt(trackwise_fields)
        prompt_name = _prompt_name_for_event(event_type)
        prompt = registry.get(prompt_name).format(formatted_fields=formatted_fields)

        result = await llm.chat(prompt)
        return {"problem_statement": result.strip()}

    except Exception:
        logger.exception("Error generating problem statement for %s", event_type)
        raise
