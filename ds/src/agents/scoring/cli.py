"""
Command-line runner for report scoring — no server or database required.

Usage:
    uv run python -m src.agents.scoring.cli "path/to/report.docx"
    uv run python -m src.agents.scoring.cli "report.docx" --event-type OOS
    uv run python -m src.agents.scoring.cli "report.docx" --json          # raw JSON only

It reads OPENAI_API_KEY from .env, sends the document through the scoring
engine, prints the % scores and the full per-checkpoint reasoning, and (unless
--json) shows a human-readable breakdown.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from src.agents.scoring.services.scoring_service import score_report
from src.llm.client import LLMClient
from src.prompt_registry.service import PromptRegistry
from src.utils import deps


def _trim(s: str, n: int) -> str:
    s = (s or "").replace("\n", " ").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _print_human(resp) -> None:
    print("\n" + "=" * 90)
    print(f"  SCORE      : {resp.score}")
    print(f"  EVENT TYPE : {resp.event_type}")
    print(f"  SECTIONS   : {', '.join(resp.detected_sections)}")
    print(f"  OVERALL    : {resp.overall_percentage}%   ({resp.overall_marks}/{resp.overall_max})")
    if resp.task_report_execution:
        g = resp.task_report_execution
        print(f"     • Task Report Execution : {g.percentage}%   ({g.marks_awarded}/{g.applicable_max})")
    if resp.iq_score:
        g = resp.iq_score
        print(f"     • IQ Score              : {g.percentage}%   ({g.marks_awarded}/{g.applicable_max})")
    print("=" * 90)

    for key in ("task_report", "rc", "impact", "capa"):
        s = resp.sections.get(key)
        if not s:
            continue
        print(f"\n  ── {s.label}  [{key}] : {s.marks_awarded}/{s.applicable_max}  ({s.percentage}%)")
        for c in s.checkpoints:
            print(f"     [{c.id}] {c.verdict:<10} {c.marks_awarded:>4}/{c.max_marks:<4} | {_trim(c.rationale, 200)}")
            if c.evidence_quote:
                print(f"            ↳ evidence: {_trim(c.evidence_quote, 140)}")
    print()


async def _run(path: Path, event_type: str | None, as_json: bool, xlsx_path: str | None) -> None:
    # Wire up the dependencies the scoring engine needs (no DB pool required).
    deps.set_llm(LLMClient())
    registry = PromptRegistry()
    registry.setup()
    deps.set_prompt_registry(registry)

    resp = await score_report(path, event_type_override=event_type)

    if xlsx_path:
        try:
            from src.agents.scoring.export.xlsx_export import build_scoring_xlsx
        except ImportError:
            raise SystemExit("XLSX export module is not present in this checkout.")
        Path(xlsx_path).write_bytes(build_scoring_xlsx(resp))
        print(f"Wrote {xlsx_path}")

    if as_json:
        print(json.dumps(resp.model_dump(), indent=2, ensure_ascii=False))
    elif not xlsx_path:
        _print_human(resp)


def main() -> None:
    parser = argparse.ArgumentParser(description="Score an investigation report (.docx / .pdf) against the rubrics.")
    parser.add_argument("file", help="Path to the .docx or .pdf report")
    parser.add_argument("--event-type", default=None, help="Deviation | OOS | OOT | Market Complaint (optional override)")
    parser.add_argument("--json", action="store_true", help="Print raw JSON instead of the readable breakdown")
    parser.add_argument("--xlsx", default=None, metavar="PATH", help="Write the scoring breakdown to an .xlsx workbook")
    args = parser.parse_args()

    path = Path(args.file)
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    asyncio.run(_run(path, args.event_type, args.json, args.xlsx))


if __name__ == "__main__":
    main()
