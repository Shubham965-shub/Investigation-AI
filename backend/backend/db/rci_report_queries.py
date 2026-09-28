"""Queries against generated_content.sql's investigation_rci_reports — one
row per investigation, upserted in place on regenerate (no attempt history,
unlike Task Critique/RC & CAPA)."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

import asyncpg

from backend.clients.db_client import get_pool


async def fetch_rci_report(deviation_id: int, rci_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    pool = get_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                "SELECT report, mc_confirmed, manual_entries, generated_at FROM investigation_rci_reports WHERE deviation_id = $1 AND rci_id IS NOT DISTINCT FROM $2",
                deviation_id,
                rci_id,
            )
        except asyncpg.exceptions.UndefinedTableError:
            return None
        if row is None:
            return None
        report = row["report"]
        manual_entries = row["manual_entries"]
        return {
            "report": (report if isinstance(report, dict) else json.loads(report)) if report else None,
            "mc_confirmed": row["mc_confirmed"],
            "manual_entries": (manual_entries if isinstance(manual_entries, dict) else json.loads(manual_entries)) if manual_entries else {},
            "generated_at": row["generated_at"],
        }


async def save_rci_report(
    deviation_id: int,
    report: Dict[str, Any],
    mc_confirmed: Optional[bool],
    manual_entries: Dict[str, str],
    rci_id: Optional[str] = None,
    generated_by: Optional[int] = None,
) -> None:
    """Called right after a fresh ds generate call — sets generated_at."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO investigation_rci_reports (deviation_id, rci_id, report, mc_confirmed, manual_entries, generated_at, updated_at, generated_by)
            VALUES ($1, $2, $3::jsonb, $4, $5::jsonb, now(), now(), $6)
            ON CONFLICT (deviation_id, rci_id) DO UPDATE SET
                report = EXCLUDED.report,
                mc_confirmed = EXCLUDED.mc_confirmed,
                manual_entries = EXCLUDED.manual_entries,
                generated_at = now(),
                updated_at = now(),
                generated_by = EXCLUDED.generated_by
            """,
            deviation_id,
            rci_id,
            json.dumps(report),
            mc_confirmed,
            json.dumps(manual_entries),
            generated_by,
        )


async def update_rci_report_sections(deviation_id: int, report: Dict[str, Any], rci_id: Optional[str] = None) -> None:
    """User edits to an already-generated report — full replace of the
    report blob only, same 'full replace on edit' convention
    updateRciPlanSections/updateEvidenceItems already use. Does not touch
    generated_at (that's set only by a real ds generate call, not an edit)."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE investigation_rci_reports SET report = $2::jsonb, updated_at = now() WHERE deviation_id = $1 AND rci_id IS NOT DISTINCT FROM $3",
            deviation_id,
            json.dumps(report),
            rci_id,
        )


async def save_rci_report_inputs(deviation_id: int, mc_confirmed: Optional[bool], manual_entries: Dict[str, str], rci_id: Optional[str] = None) -> None:
    """Lets the mc_confirmed toggle / manual entries persist as the
    investigator fills them in, even before the first generate call —
    upserts a placeholder row with report still NULL."""
    pool = get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO investigation_rci_reports (deviation_id, rci_id, mc_confirmed, manual_entries)
            VALUES ($1, $2, $3, $4::jsonb)
            ON CONFLICT (deviation_id, rci_id) DO UPDATE SET
                mc_confirmed = EXCLUDED.mc_confirmed,
                manual_entries = EXCLUDED.manual_entries,
                updated_at = now()
            """,
            deviation_id,
            rci_id,
            mc_confirmed,
            json.dumps(manual_entries),
        )
