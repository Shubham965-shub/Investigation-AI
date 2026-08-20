"""
Construct and compile the LangGraph search agent.
Provides the topology for keyword, semantic, and hybrid search methods.
"""
from __future__ import annotations

from functools import partial
import asyncpg
from langgraph.graph import END, StateGraph

from src.agents.search_agent.graph.edges import route_by_search_type
from src.agents.search_agent.graph.nodes import (
    analyze_query,
    combine_results_node,
    keyword_search_node,
    relevance_filter_node,
    rerank_candidates_node,
    semantic_search_node,
)
from src.agents.search_agent.graph.state import SearchState
from src.llm.client import LLMClient


def build_search_graph(pool: asyncpg.Pool, llm: LLMClient):
    """
    Build the main search state graph and return the compiled application.
    
    The graph integrates keyword and semantic nodes, dynamically routing 
    based on the analyzed query constraints.
    """
    search_graph = StateGraph(SearchState)

    # Nodes Definition
    search_graph.add_node("analyze_query", partial(analyze_query, llm=llm))
    search_graph.add_node("keyword_search", partial(keyword_search_node, pool=pool))
    search_graph.add_node("semantic_search", partial(semantic_search_node, pool=pool, llm=llm))
    search_graph.add_node("combine_results", combine_results_node)
    search_graph.add_node("rerank_candidates", partial(rerank_candidates_node, llm=llm))
    search_graph.add_node("relevance_filter", partial(relevance_filter_node, llm=llm))

    # Flow Configuration
    search_graph.set_entry_point("analyze_query")

    search_graph.add_conditional_edges(
        "analyze_query",
        route_by_search_type,
        {
            "keyword_only": "keyword_search",
            "semantic_only": "semantic_search",
            "hybrid": "keyword_search", 
        },
    )

    def decide_post_keyword_route(state: SearchState) -> str:
        """Depending on search type, either stop at keyword or continue to semantic."""
        search_type = (state.get("determined_search_type") or "").lower()
        if search_type == "hybrid":
            return "semantic_search"
        return "combine_results"

    search_graph.add_conditional_edges(
        "keyword_search",
        decide_post_keyword_route,
        {
            "combine_results": "combine_results",
            "semantic_search": "semantic_search",
        },
    )

    search_graph.add_edge("semantic_search", "combine_results")

    search_graph.add_edge("combine_results", "rerank_candidates")
    search_graph.add_edge("rerank_candidates", "relevance_filter")
    search_graph.add_edge("relevance_filter", END)

    return search_graph.compile()


# NOTE — True Parallel Search
# ----------------------------
# The graph above runs keyword → semantic sequentially.  If you need
# true parallelism, replace keyword_search and semantic_search with a
# single "parallel_search" node that internally does:
#
#   async def parallel_search(state, pool, llm):
#       kw, sem = await asyncio.gather(
#           keyword_search_node(state, pool),
#           semantic_search_node(state, pool, llm),
#       )
#       return {**kw, **sem}
#
# Then wire:  analyze_query → parallel_search → combine_results → ...
