from src.llm.client import LLMClient
from src.agents.search_agent.graph.state import SearchState
from src.config.settings import settings
from src.agents.search_agent.api.schemas import (
    SearchRequest
)
import logging

logger = logging.getLogger(__name__)

# ── Executive Summary Functions ────────────────────────────────

async def _get_executive_narrative(state: SearchState, body: SearchRequest) -> str:
    """Generate executive summary from search results using LLM."""
    
    # Load the executive summary prompt
    prompt_path = settings.PROMPTS_DIR / "search_agent" / "executive_narrative.txt"
    with open(prompt_path, 'r') as f:
        prompt_template = f.read()

    ranked = get_final_ranked_results(state)

    if not ranked:
        return "No results found to generate executive summary."
    
    root_cause_category_counts = {}
    for r in ranked:
        if not r['root_cause_category'] in root_cause_category_counts:
            root_cause_category_counts[r['root_cause_category']] = 1
        else:
            root_cause_category_counts[r['root_cause_category']] += 1
    
    top_root_cause_category = max(root_cause_category_counts, key = root_cause_category_counts.get)    
    top_cause_list = [
        r for r in ranked
        if r.get('root_cause_category') == top_root_cause_category
    ][:15]

    # Extract time period from filters
    filters = state.get("filters", {})
    date_range = filters.get("date_range", "all")
    if date_range == "all":
        time_period = "all available data"
    else:
        time_period = f"last {date_range.replace('_', ' ')}"
    
    # Prepare results context (top 20 results to stay within limits)
    id_col = settings.COLUMN_ID
    desc_col = settings.COLUMN_DESCRIPTION
    root_col = settings.COLUMN_ROOT_CAUSE
    cat_col = settings.COLUMN_CATEGORY
    loc_col = settings.COLUMN_LOCATION
    prod_col = getattr(settings, 'COLUMN_PRODUCT', 'product')
    
    results_context = "\n\n".join(
        f"[ID={r.get(id_col) or r.get('id')}] "
#        f"Description: {r.get(desc_col) or r.get('description', 'N/A')}\n"
        f"Root Cause: {r.get(root_col) or r.get('root_cause_summary', 'N/A')}\n"
        f"Category: {r.get(cat_col) or r.get('category', 'N/A')}\n"
        f"Location: {r.get(loc_col) or r.get('location', 'N/A')}\n"
        f"Product: {r.get(prod_col) or r.get('product', 'N/A')}"
        for r in top_cause_list
    )
    category_context = f"Top root cause category: {top_root_cause_category}\n"
    
    prompt = prompt_template.format(
        query=state["query"],
        time_period=time_period,
        total_results=len(ranked),
        results_context=results_context,
        category = category_context
    )
    
    try:
        llm = LLMClient()
        response = await llm.chat(prompt)
        return response.strip()
    except Exception as exc:
        logger.error("Executive summary generation failed: %s", exc)
        return "Unable to generate executive summary at this time."

async def _get_top_cause_description(state: SearchState, body: SearchRequest) -> str:
    """Generate top cause description from search results using LLM."""
    
    # Load the top causes prompt
    prompt_path = settings.PROMPTS_DIR / "search_agent" / "top_cause_analysis.txt"
    with open(prompt_path, 'r') as f:
        prompt_template = f.read()
    
    ranked = get_final_ranked_results(state)

    if not ranked:
        return "No results found to analyze root causes."
    
    root_cause_category_counts = {}
    for r in ranked:
        if not r['root_cause_category'] in root_cause_category_counts:
            root_cause_category_counts[r['root_cause_category']] = 1
        else:
            root_cause_category_counts[r['root_cause_category']] += 1


    # Prepare results context (top 15 results for focused analysis)
    top_root_cause_category = max(root_cause_category_counts, key = root_cause_category_counts.get)    
    top_cause_list = [
        r for r in ranked
        if r.get('root_cause_category') == top_root_cause_category
    ][:15]


    id_col = settings.COLUMN_ID
#    desc_col = settings.COLUMN_DESCRIPTION
    root_col = settings.COLUMN_ROOT_CAUSE
    cat_col = settings.COLUMN_CATEGORY
    
    results_context = "\n\n".join(
        f"[ID={r.get(id_col) or r.get('id')}] "
#        f"Description: {r.get(desc_col) or r.get('description', 'N/A')}\n"
        f"Root Cause: {r.get(root_col) or r.get('root_cause_summary', 'N/A')}\n"
        f"Category: {r.get(cat_col) or r.get('category', 'N/A')}\n"
        for r in top_cause_list
    )
    top_cause_context = f"Top root cause category: {top_root_cause_category}\n"
    
    prompt = prompt_template.format(
        query=state["query"],
        total_results=len(ranked),
        results_context=results_context,
        top_cause_context = top_cause_context
    )
    
    try:
        llm = LLMClient()
        response = await llm.chat(prompt)
        return response.strip()

    except Exception as exc:
        logger.error("Top cause analysis failed: %s", exc)
        return "Unable to analyze top causes at this time."

async def _get_capa_recurring_themes(state: SearchState) -> list[str]:
    """TODO: Replace this dummy function with real LLM extraction logic later."""
    return ["SOP Misalignment", "Material Handling", "Maintenance"]

def get_final_ranked_results(state: SearchState) -> list[dict]:
    """
    Final unified output of the search pipeline.
    """
    return state.get("final_results", [])
