import asyncpg
import json
import logging
from typing import Any, Dict, List

from src.agents.rci_plan.state import RciPlanState
from src.config.settings import settings
from src.utils.deps import get_llm_client, get_prompt_registry

logger = logging.getLogger(__name__)


async def fetch_rci_plan(state: RciPlanState) -> RciPlanState:
    """Fetch RCI plan templates (sections & tasks) for the mapped archetype."""
    if state.mapped_archetype.get("id") is None:
        state.rci_plan_original = []
        return state

    # settings.DATABASE_URL (not a raw f-string) — DB_PASSWORD contains
    # characters (#, ,) that are URL-structural if not percent-encoded;
    # unencoded, asyncpg fails to parse the DSN at all, silently caught by
    # the except below and turning every call into "no archetype found".
    db_url = settings.DATABASE_URL
    try:
        conn = await asyncpg.connect(db_url)
        try:
            # Fetch the RciPlan for this archetype
            plan_row = await conn.fetchrow(
                "SELECT id FROM rci_plan WHERE archetype_id = $1",
                state.mapped_archetype["id"]
            )
            if not plan_row:
                state.rci_plan_original = []
                logger.info(f"No RCI plan template found for archetype: {state.mapped_archetype['name']}")
                return state

            plan_id = plan_row["id"]

            # Fetch the sections
            section_rows = await conn.fetch(
                "SELECT id, title, correlation FROM rci_plan_section WHERE rci_plan_id = $1 ORDER BY id",
                plan_id
            )

            sections = []
            for sec in section_rows:
                # Fetch tasks for each section
                task_rows = await conn.fetch(
                    "SELECT description FROM rci_plan_task WHERE rci_plan_section_id = $1 ORDER BY id",
                    sec["id"]
                )
                sections.append({
                    "title": sec["title"],
                    "correlation": sec["correlation"],
                    "tasks": [{"description": r["description"]} for r in task_rows]
                })

            state.rci_plan_original = sections
            logger.info(f"Fetched {len(sections)} sections for RCI plan template")
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"Error fetching RCI plan: {e}")
        state.rci_plan_original = []
    return state


async def rephrase_rci_plan(state: RciPlanState) -> RciPlanState:
    """Contextualise the RCI plan sections and tasks using trackwise fields."""
    if not state.rci_plan_original:
        state.rci_plan_rephrased = []
        return state

    try:
        llm = await get_llm_client()
    except Exception:
        from src.llm.client import LLMClient
        llm = LLMClient()

    registry = get_prompt_registry()
    
    # Format the original plan to string
    rci_plan_list = []
    for sec in state.rci_plan_original:
        tasks_str = "\n".join(f"  - {t['description']}" for t in sec["tasks"])
        corr_str = f" (Correlation: {sec['correlation']})" if sec.get("correlation") else ""
        rci_plan_list.append(f"Section: {sec['title']}{corr_str}\nTasks:\n{tasks_str}")
    rci_plan_str = "\n\n".join(rci_plan_list)

    tw_fields_str = "\n".join(f"- {k}: {v}" for k, v in state.trackwise_fields.items() if v)
    
    prompt = registry.get("rci_plan/rephrase_rci_plan").format(
        event_type=state.event_type,
        tw_fields_str=tw_fields_str,
        rci_plan_str=rci_plan_str,
    )

    result = await llm.chat(prompt)
    try:
        rephrased = json.loads(result.strip())
        if not isinstance(rephrased, list):
            raise ValueError("Expected a JSON array")
    except Exception:
        logger.error(f"RCI plan rephrase JSON parse failed, using originals. LLM output: {result}")
        rephrased = state.rci_plan_original

    # Normalize structure to match expected state.rci_plan_rephrased
    state.rci_plan_rephrased = []
    for sec in rephrased:
        title = sec.get("title", "Section")
        correlation = sec.get("correlation")
        tasks = []
        for t in sec.get("tasks", []):
            if isinstance(t, dict):
                tasks.append({"description": t.get("description", "")})
            elif isinstance(t, str):
                tasks.append({"description": t})
            else:
                tasks.append({"description": str(t)})
        state.rci_plan_rephrased.append({
            "title": title,
            "correlation": correlation,
            "tasks": tasks
        })

    logger.info(f"Rephrased {len(state.rci_plan_rephrased)} sections for RCI plan")
    return state


async def format_result(state: RciPlanState) -> RciPlanState:
    """Format final response structure."""
    sections = state.rci_plan_rephrased if state.rci_plan_rephrased else state.rci_plan_original
    
    total_tasks = sum(len(sec.get("tasks", [])) for sec in sections)
    
    state.final_result = {
        "event_type": state.event_type,
        "failure_type": state.failure_type or "Unknown",
        "archetype": {
            "id": state.mapped_archetype.get("id") if state.mapped_archetype else None,
            "name": state.mapped_archetype.get("name") if state.mapped_archetype else "Unknown",
            "is_new": state.is_new_archetype,
            "confidence_score": state.confidence_score,
            "reasoning": state.reasoning,
        },
        "sections": sections,
        "total_sections_count": len(sections),
        "total_tasks_count": total_tasks,
    }
    return state


# Historical path commented out as per user request:
# async def infer_rci_plan_from_historical_data(state: RciPlanState) -> RciPlanState:
#     """Infer RCI plan from historical incidents."""
#     # No historical path needed for RCI plan
#     pass
