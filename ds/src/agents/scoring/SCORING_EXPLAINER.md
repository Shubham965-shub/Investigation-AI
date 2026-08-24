# Investigation Report Scoring — Explainer

This document explains **how a completed investigation report is scored** and **where the reasoning for each mark comes from**. It's meant to be readable by a non-engineer (e.g. to walk a PM through the logic). The per-report Excel export (`/score/report/xlsx` or the CLI `--xlsx`) contains the same breakdown for a specific report.

---

## The two reports

A report is scored against **two marking checklists**, producing **two report scores**, which are then **consolidated into one final percentage**.

| Report | Covers | Out of |
|---|---|---|
| **Report 1 — Task Report Execution** | The investigation task report | **40** |
| **Report 2 — IQ Score** | Root Cause (30) + Impact (10) + CAPA (20) | **60** |
| **Final consolidated score** | Both, combined | **100 → shown as %** |

`Final % = (Report 1 marks + Report 2 marks) ÷ (applicable maximums) × 100`. Only the sections actually present in the uploaded document are counted (so a CAPA-only upload is scored out of CAPA's marks alone).

---

## How each checkpoint is scored

An AI assessor reads the report and returns, for every checkpoint: a **verdict**, a **rationale** (why), and a **verbatim evidence quote** from the report. The **marks are then computed in code** — the AI never assigns numbers itself, so the maths is deterministic and auditable.

- **Binary rows** — the required content is present & adequate → full marks for that row, else 0.
- **Divided criteria** — where a criterion has several rows, the marks are split evenly across the rows and each row is scored on its own, so a criterion can be *partly* met. Example: Impact 6.1 has 4 rows worth 1 each; 3 of 4 present = **3/4**.
- **Root Cause** — a single choice by strength of evidence: **No cause = −5**, **Probable = 10**, **Assignable = 30**.
- **CAPA (7.2)** — scored by **effectiveness level** of the strongest action proposed: **L1 = 4, L2 = 4, L3 = 8, L4 = 10, L5 = 10**; no adequate CAPA = **0**.
- **"NA"** — only used where the checklist allows it *and* the report explicitly justifies non-applicability. If the report is simply silent, the row scores **0** (it is not excused).

**Reliability:** each section is scored several times and the **majority verdict** per checkpoint is taken (self-consistency), which steadies borderline judgements.

---

## Report 1 — Task Report Execution (/40)

| Sub-criteria | Checkpoint | Marks |
|---|---|---|
| 2.2 Title & Objective | 1 — each task has a clear, specific title | 4 |
| | 2 — each task states a specific, answerable objective | 4 |
| 3.1 Evidence & Objectivity | 3 — findings supported by objective evidence & data | 6 |
| | 4 — both confirming & disconfirming evidence; quantified | 4 |
| 3.2 Completeness & Traceability | 5 — every part of the task is completed; any gap is declared, not left open | 4 |
| | 6 — data traceable to a named, authenticated source record (ALCOA+) | 6 |
| 4.1 Logical Linkage & Depth | 7 — each inference follows from findings | 4 |
| | 8 — ruled-out causes justified; listed factors examined *(NA allowed)* | 4 |
| | 9 — inferences give a gap-free basis for root cause, explained clearly even if no root cause | 4 |
| **Total** | | **40** |

## Report 2 — IQ Score (/60)

**Root Cause (/30)** — pick one: No cause (−5) · Probable (10) · Assignable (30).

**Impact (/10)**

| Sub-criteria | Rows | Each | Max |
|---|---|---|---|
| 6.1 Impact on current batch | 4 (impact identified; HHE; regulatory/market notification; continuation of production) | 1 | 4 |
| 6.2 Extended impact | 2 (impact on others stated; rationale if only current) | 2 | 4 |
| 6.3 Batch disposition | 1 | 2 | 2 |

**CAPA (/20)**

| Sub-criteria | Scoring | Max |
|---|---|---|
| 7.1 Correction | 2 rows × 1 (addresses effect; no adverse quality impact) | 2 |
| 7.2 CAPA | effectiveness level L1..L5 = 4/4/8/10/10 (or none = 0) | 10 |
| 7.3 Interim control | present with objective/owner/timeline *(NA allowed)* | 4 |
| 7.4 Effectiveness check | present with objective/owner/timeline *(NA allowed)* | 4 |

### CAPA effectiveness levels (7.2)

Higher level = more robust / systemic action = more marks:

- **L1 (4)** — awareness / personnel-dependent only (training, re-instruction, communication), or no adequate action.
- **L2 (4)** — procedural / documentation change (SOP / BMR / protocol revision, added checklist or review) — still relies on human compliance.
- **L3 (8)** — an enhanced control or detection is added (new in-process check, alarm, interlock, poka-yoke aid, more sampling).
- **L4 (10)** — engineering / process redesign (equipment modification, automation, mistake-proofing that removes the human decision).
- **L5 (10)** — elimination of the hazard / failure mode (the step or material is designed out entirely).

---

## Where everything is stored (database)

**Server:** `azure_qa` (`qa-lighthouse-db`) · **Database:** `investigation_ai` · **Schema:** `public`. All four tables are prefixed `investigation_ai_`.

**A. The checklists (the rubric itself)** — reference data, one-time loaded from the code:

| Table | Holds | Key columns |
|---|---|---|
| `investigation_ai_checklist_section` | the 4 sections | `section`, `label`, `native_max`, `achievable_max` |
| `investigation_ai_checklist_checkpoint` | all 25 checkpoints | `section`, `checkpoint_id`, `sub_criteria`, `checkpoint_text`, `max_marks`, `kind` (binary/classification), `allow_na`, `tiers` (RC & CAPA-level marks, JSON) |

**B. The scored results (the "why")** — written once per scored report:

| Table | Holds | Key columns |
|---|---|---|
| `investigation_ai_report_score` | one row per scored report | `id`, `created_at`, `filename`, `event_type`, `detected_sections`, `score` (final %), `overall_marks`/`overall_max`, `task_report_percentage`, `iq_percentage`, `breakdown` (full JSON snapshot) |
| `investigation_ai_report_score_checkpoint` | one row per checkpoint = the evidence | `run_id` (→ report_score.id), `section`, `checkpoint_id`, `verdict`, `marks_awarded`, `max_marks`, `applicable`, `rationale`, `evidence_quote` |

**To see exactly why a report scored what it did:**

```sql
SELECT c.section, c.checkpoint_id, c.verdict, c.marks_awarded, c.max_marks, c.rationale, c.evidence_quote
FROM investigation_ai_report_score_checkpoint c
JOIN investigation_ai_report_score r ON r.id = c.run_id
WHERE r.id = '<run id>'          -- or filter on r.filename
ORDER BY c.section, c.checkpoint_id;
```

**When results are written:** automatically on the API path (`POST /score/report`), best-effort, when the app is connected to the `investigation_ai` database. (The local CLI scores but does not persist.) The same per-checkpoint verdict + rationale + evidence is also returned in the API response and laid out in the Excel export's "Task Report" and "IQ Score" sheets.
