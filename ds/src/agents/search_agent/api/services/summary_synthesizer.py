import random
import json
import logging
from collections import defaultdict
from typing import List, Any
from src.llm.client import LLMClient
from src.agents.search_agent.api.schemas import (
    SynthResponse,
    RootCauseData,
    CAPAData,
    EventData,
    SynthType,
    ERSynth
)
from src.config.settings import settings
from dataclasses import dataclass
from typing import Type, Generic, TypeVar

logger = logging.getLogger(__name__)

llm = LLMClient()

T = TypeVar("T")  # category payload


@dataclass
class SynthConfig(Generic[T]):
    response_model: Type[SynthResponse[T]]
    prompt: str

def _load_prompt(filename: str) -> str:
    """Load a prompt template from the centralized prompts directory."""
    if filename == "guardrail.txt":
        prompt_path = settings.PROMPTS_DIR / filename
        return prompt_path.read_text(encoding="utf-8")
    prompt_path = settings.PROMPTS_DIR / "search_agent" / filename
    return prompt_path.read_text(encoding="utf-8")

guard_rail_text = _load_prompt("guardrail.txt")
rcs_prompt = _load_prompt("rcs_summary.txt")
capa_prompt = _load_prompt("capa_summary.txt")
event_prompt = _load_prompt("event_summary.txt")

from typing import Type, Any

class RootCauseResponse(SynthResponse[RootCauseData]):
    pass

class CAPAResponse(SynthResponse[CAPAData]):
    pass


SYNTH_CONFIG: dict[SynthType, SynthConfig] = {
    SynthType.RC: SynthConfig(
        response_model=RootCauseResponse,
        prompt=rcs_prompt,
    ),
    SynthType.CAPA: SynthConfig(
        response_model=CAPAResponse,
        prompt=capa_prompt,
    ),
    SynthType.EVENT: SynthConfig(
        response_model=ERSynth,
        prompt=event_prompt,
    ),
}

async def get_synth_summary(
    records: List[Any],
    synth_type: SynthType,
):
    if synth_type not in SYNTH_CONFIG:
        raise ValueError(f"Unsupported synth type: {synth_type}")

    config = SYNTH_CONFIG[synth_type]

    try:
        payload = prepare_llm_input(records)
        
        total_events, site_wise_events = compute_event_metrics(records)

        
        count_details = (
            "\n\nIMPORTANT CONSTRAINTS:\n"
            f"- Total number of input records (events): {total_events}\n"
            f"- Site-wise event counts:\n"
            + "\n".join(
                f"  - {site}: {count}"
                for site, count in site_wise_events.items()
            )
            + "\n"
            "- Do NOT invent, assume, or extrapolate additional events\n"
            "- All counts, trends, and summaries MUST strictly align with these numbers\n"
        )

        prompt_with_counts = config.prompt + count_details

        result = await run_llm(
            payload=payload,
            prompt=prompt_with_counts,
            response_model=config.response_model,
        )
        logger.info(f"LLM response is generated")

        return result.response

    except Exception as exc:
        logger.exception(
            f"Failed to generate {synth_type} synthesis",
            exc_info=exc,
        )
        raise



def prepare_llm_input(records: List[Any]) -> list[dict]:
    grouped = group_by_site_and_category(records)
    payload = build_category_payload(grouped)

    logger.info(
        "Built site payload",
        extra={
            "site_count": len(payload),
            "category_count": sum(len(site["categories"]) for site in payload),
        },
    )
    return payload

async def run_llm(
    payload: list[dict],
    prompt: str,
    response_model: Type[SynthResponse[T]],
) -> SynthResponse[T]:
    return await llm.get_structured_response(
        system_prompt=guard_rail_text,
        user_prompt=f"{prompt}\n\nINPUT:\n{json.dumps(payload)}",
        structure=response_model,
    )

def normalize_ids(ids: list) -> tuple[list, bool]:
    """
    Returns (normalized_ids, use_text)
    """
    try:
        return [int(x) for x in ids], False
    except Exception:
        return [str(x) for x in ids], True

def group_by_site_and_category(records: list[Any]) -> dict[str, dict[str, list[Any]]]:
    
    grouped: dict[str, dict[str, list[Any]]] = defaultdict(lambda: defaultdict(list))

    for r in records:
        site = getattr(r, "site", None) or "Unknown Site"
        category = getattr(r, "root_cause_category", None) or "Uncategorized"
        grouped[site][category].append(r)


    return grouped

def build_category_payload(
    grouped_records: dict[str, dict[str, list[Any]]]
) -> list[dict]:
    payload = []

    for site, categories in grouped_records.items():
        site_categories = []

        for category, recs in categories.items():
            sampled = sorted(
                random.sample(recs, min(len(recs), 15)),
                key=lambda r: getattr(r, "deviation_id", ""),
            )

            items = []
            for r in sampled:
                summary = getattr(r, "root_cause_summary", None)
                age_bucket = getattr(r, "age_bucket", None)

                if not summary:
                    continue

                # Fallback label if age_bucket is missing
                if age_bucket:
                    age_label = age_bucket
                    items.append(
                    f"[{age_label}] {r.deviation_id} → {summary}"
                    )
                else:
                    items.append(
                    f"{r.deviation_id}: {summary}"
                    )

            if not items:
                continue

            site_categories.append({
                "category": category,
                "items": items,
            })

        if site_categories:
            payload.append({
                "site": site,
                "categories": site_categories,
            })

    return payload

def format_response_for_ui(synth_type: SynthType, response):
    formatted = []

    for site in response:
        base = {
            "site": site.site,
            "total": site.total,
        }

        # RC + EVENT → sections
        if synth_type in {SynthType.RC}:
            base["sections"] = [
                {
                    "title": c.category,
                    **c.data.model_dump(),
                }
                for c in site.categories
            ]

        # CAPA → categories
        elif synth_type == SynthType.CAPA:
            base["categories"] = [
                {
                    "category": c.category,
                    **c.data.model_dump(),
                }
                for c in site.categories
            ]
        
        elif synth_type == SynthType.EVENT:
            categories = []

            for c in site.categories:
                # Extract enum value safely
                title_enum = c.title[0].value if c.title else None

                # Convert: 0_to_6_months → 0_6_months
                ui_title = title_enum.replace("_to_", "_") if title_enum else None

                # Convert list[str] → dict {deviation_id: summary}
                items_list = []
                for item in c.items:
                    if ":" in item:
                        deviation_id, summary = item.split(":", 1)
                        items_list.append(f"{deviation_id.strip()} : {summary.strip()}")

                trend = c.trend

                categories.append(
                    {
                        "title": ui_title,
                        "items": items_list,
                        "trend": trend
                    }
                )

            base.update(
                {
                    "site": site.site,
                    "total": int(site.total) if site.total else 0,
                    "categories": categories,
                }
            )


        formatted.append(base)

    return formatted


def compute_event_metrics(records: list[Any]) -> tuple[int, dict[str, int]]:
    """
    Returns:
    - total_events
    - site_wise_event_counts
    """
    site_counts: dict[str, int] = defaultdict(int)

    for r in records:
        site = getattr(r, "site", None) or "Unknown Site"
        site_counts[site] += 1

    return len(records), dict(site_counts)