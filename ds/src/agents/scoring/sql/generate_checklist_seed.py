"""
Generate the DDL + seed for the scoring checklist tables from rubric_config.

The scoring engine's source of truth is `rubric_config.py`. Rather than hand-write
the SQL (and risk drift), this script emits the DDL + INSERTs straight from that
config so the database copy always matches the code.

Layout: the tables live in the `public` schema, prefixed with `investigation_ai_`
(moved out of the former dedicated `task_report_critique` schema):
    public.investigation_ai_checklist_section
    public.investigation_ai_checklist_checkpoint

Run:  uv run python -m src.agents.scoring.sql.generate_checklist_seed
Emits: src/agents/scoring/sql/investigation_ai_checklists.sql

Apply against the investigation_ai database on the azure_qa (qa-lighthouse-db) server:
      psql "<investigation_ai connection string>" -f investigation_ai_checklists.sql
"""

from __future__ import annotations

import json
from pathlib import Path

from src.agents.scoring.rubric.rubric_config import ALL_SECTION_KEYS, get_section

SECTION_TABLE = "public.investigation_ai_checklist_section"
CHECKPOINT_TABLE = "public.investigation_ai_checklist_checkpoint"

_SOURCE = {
    "task_report": "Task_Report_Execution_Rubric_40marks.docx",
    "rc": "IQ _ RC ,IMPACT & CAPA .xlsx",
    "impact": "IQ _ RC ,IMPACT & CAPA .xlsx",
    "capa": "IQ _ RC ,IMPACT & CAPA .xlsx",
}

_HEADER = f"""-- ============================================================================
-- Scoring checklist tables (public schema)
-- Database: investigation_ai   (server: azure_qa / qa-lighthouse-db)
--
-- Holds the marking checklists used to score investigation reports:
--   * Task Report Execution rubric  (/40)
--   * IQ Score rubric — RC (/30), Impact (/10), CAPA (/20)  → /60
--
-- Tables live in the public schema, prefixed with investigation_ai_ (moved out of
-- the former dedicated task_report_critique schema, which is dropped below).
--
-- GENERATED from src/agents/scoring/rubric/rubric_config.py — do not edit by hand.
-- Regenerate: uv run python -m src.agents.scoring.sql.generate_checklist_seed
-- Idempotent: safe to re-run (ON CONFLICT DO UPDATE keeps the DB in sync with code).
-- ============================================================================

-- Remove the previous dedicated schema (its tables are relocated below).
DROP SCHEMA IF EXISTS task_report_critique CASCADE;

CREATE TABLE IF NOT EXISTS {SECTION_TABLE} (
    section         text PRIMARY KEY,          -- task_report | rc | impact | capa
    label           text        NOT NULL,
    native_max      numeric     NOT NULL,       -- section total as printed on the source checklist
    achievable_max  numeric     NOT NULL,       -- sum of checkpoint maxima (max earnable)
    source          text        NOT NULL,       -- originating checklist file
    display_order   int         NOT NULL
);

CREATE TABLE IF NOT EXISTS {CHECKPOINT_TABLE} (
    section         text        NOT NULL REFERENCES {SECTION_TABLE}(section) ON DELETE CASCADE,
    checkpoint_id   text        NOT NULL,        -- e.g. '6.1a', '1'
    sub_criteria    text        NOT NULL,
    checkpoint_text text        NOT NULL,
    max_marks       numeric     NOT NULL,        -- marks awarded when satisfied
    kind            text        NOT NULL DEFAULT 'binary',   -- binary | classification
    allow_na        boolean     NOT NULL DEFAULT false,
    tiers           jsonb,                        -- null unless kind='classification' (e.g. RC tiers)
    display_order   int         NOT NULL,
    PRIMARY KEY (section, checkpoint_id)
);

-- These tables are a code-generated mirror of rubric_config.py — clear and
-- reload so removed/renamed checkpoints never linger as stale rows.
DELETE FROM {CHECKPOINT_TABLE};
DELETE FROM {SECTION_TABLE};
"""


def _q(value: str) -> str:
    """SQL single-quote literal."""
    return "'" + value.replace("'", "''") + "'"


def build_sql() -> str:
    lines = [_HEADER]

    lines.append("\n-- ── Sections ────────────────────────────────────────────────────────────────")
    for order, key in enumerate(ALL_SECTION_KEYS, start=1):
        spec = get_section(key)
        lines.append(
            f"INSERT INTO {SECTION_TABLE} "
            "(section, label, native_max, achievable_max, source, display_order) VALUES\n"
            f"    ({_q(spec.section)}, {_q(spec.label)}, {spec.native_max}, "
            f"{spec.achievable_max}, {_q(_SOURCE[key])}, {order})\n"
            "ON CONFLICT (section) DO UPDATE SET\n"
            "    label = EXCLUDED.label, native_max = EXCLUDED.native_max,\n"
            "    achievable_max = EXCLUDED.achievable_max, source = EXCLUDED.source,\n"
            "    display_order = EXCLUDED.display_order;"
        )

    lines.append("\n-- ── Checkpoints ─────────────────────────────────────────────────────────────")
    for key in ALL_SECTION_KEYS:
        spec = get_section(key)
        for order, cp in enumerate(spec.checkpoints, start=1):
            tiers_sql = "NULL" if cp.tiers is None else f"{_q(json.dumps(cp.tiers))}::jsonb"
            lines.append(
                f"INSERT INTO {CHECKPOINT_TABLE} "
                "(section, checkpoint_id, sub_criteria, checkpoint_text, max_marks, kind, allow_na, tiers, display_order) VALUES\n"
                f"    ({_q(spec.section)}, {_q(cp.id)}, {_q(cp.sub_criteria)}, {_q(cp.text)}, "
                f"{cp.max_marks}, {_q(cp.kind)}, {str(cp.allow_na).lower()}, {tiers_sql}, {order})\n"
                "ON CONFLICT (section, checkpoint_id) DO UPDATE SET\n"
                "    sub_criteria = EXCLUDED.sub_criteria, checkpoint_text = EXCLUDED.checkpoint_text,\n"
                "    max_marks = EXCLUDED.max_marks, kind = EXCLUDED.kind, allow_na = EXCLUDED.allow_na,\n"
                "    tiers = EXCLUDED.tiers, display_order = EXCLUDED.display_order;"
            )

    return "\n".join(lines) + "\n"


def main() -> None:
    out_path = Path(__file__).with_name("investigation_ai_checklists.sql")
    out_path.write_text(build_sql(), encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
