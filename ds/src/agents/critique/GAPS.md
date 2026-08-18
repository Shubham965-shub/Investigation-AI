# Critique Agent (Task Report Critique + RC & CAPA Critique) — Open Items

Task Report Critique: `POST /critique/analyse-task-report` (`api/routes/task_report_critique_route.py`,
graph in `graph/`). RC & CAPA Critique: `POST /critique/critique-rc-conclusion` and
`POST /critique/critique-capa` (`api/routes/critique_route.py`). Follow `rci_report/GAPS.md`'s
convention going forward: append new dated entries here as real issues are found and fixed during
live testing, rather than converting this into a status table.

## 2026-08-12 — Carry forward accepted-but-unaddressed recommendations across re-uploads (DS-only at the time; backend change landed 2026-08-14, see below)

An investigator can upload up to 3 attempts of a task report per task (`task_index`), via the
backend's `POST /task-critique/{record_id}/sections/{task_index}/upload`. Until now, every
re-upload was critiqued from scratch — if the investigator accepted a recommendation on attempt 1
but their attempt 2 report still didn't actually address it, that gap silently disappeared instead
of being raised again. Built (per the user, 2026-08-12) so an accepted-but-still-unaddressed
recommendation is regenerated on the next attempt, explicitly saying so, alongside any genuinely
new gaps found.

Scope was deliberately narrowed to DS only (per the user) — no `backend/backend/**` changes in
this session. RC & CAPA Critique was explicitly excluded (its `investigation_rc_capa_reports` table
already keeps one full row per attempt rather than overwriting in place, so it doesn't have this
same problem, and confirmed out of scope).

**How this works without a backend change**: DS already holds its own direct connection to the
same shared Postgres instance (`ds/.env`'s `DB_*` vars → `src/db/pool.py` →
`src/utils/deps.get_db_pool()`, the same pattern `scoring/services/persistence.py` and
`search_agent` already use) — it can read `investigation_task_critique_reports` and
`investigation_task_critique_recommendation_history` directly, without the backend handing it any
recommendation data. New node `fetch_previous_recommendations` (`graph/nodes.py`, wired into
`graph/graph.py` between `extract_tasks` and `analyze_images`) queries both tables for a given
`(deviation_id, task_index)`:
- `investigation_task_critique_recommendation_history`, most recent row by `created_at`, for the
  previous attempt's recommendation *text* (this table is written once at generation time and
  never carries a decision — it's a write-once audit log by design).
- `investigation_task_critique_reports`' current row for that same `(deviation_id, task_index)`,
  which still holds that same previous attempt's final *decisions* — because the backend's
  `upload_task_report` calls this endpoint **before** it overwrites that row for the new attempt
  (explicit comment in `task_critique.py`: "Called BEFORE persisting anything, so a transient DS
  failure doesn't burn one of the 3 real upload attempts").

Both lists come from the identical ordered list written in the same backend call
(`save_critique`/`insert_recommendation_history` fire back-to-back with the same `recommendations`
list), so they're zipped by index; anything with `decision == "accepted"` is passed to
`critique_tasks` as `previous_recommendations`. `critique_task.yaml` v6 instructs the LLM to check
each against the new report's content, drop resolved ones, and regenerate unresolved ones prefixed
with the exact phrase `Still unaddressed from the previous review.` — a fixed marker that's both
what the investigator sees and what `critique_tasks`' post-LLM cap sorts on to keep carried-forward
items ahead of new ones within the existing 5-per-task limit.

**Backend change required, not yet done (flagging per the user's explicit instruction)**:
`POST /critique/analyse-task-report` now accepts two new optional form fields,
`deviation_id: Optional[int]` and `task_index: Optional[int]`, alongside the existing `file`. Until
`backend/backend/routers/task_critique.py`'s `upload_task_report` is updated to send both in its
existing multipart call, both default to `None` and this entire feature is inert —
`fetch_previous_recommendations` short-circuits to an empty list and every request behaves exactly
as it did before this change (verified: `.format()` renders `{previous_recommendations}` as the
literal text "None." in that case, an added-but-inert prompt section).

**Invariant this relies on, worth re-checking when the backend side is wired up**: DS's read of
`investigation_task_critique_reports`' current row is only correct because the backend calls DS
*before* overwriting that row for the new attempt. If that call order ever changes (e.g. the
backend starts persisting the new attempt's row first), this cross-reference would silently break
— it would end up reading the *new*, just-created attempt's blanked-out row (`recommendations =
'[]'`, per `upsert_report`) instead of the previous attempt's decided one, and
`previous_recommendations` would always come back empty with no error raised.

**Not yet live-tested** — no coordinated backend request exists yet to exercise this end-to-end. Can
be smoke-tested directly against the DS endpoint today by calling it with a real `deviation_id`/
`task_index` that has a prior `investigation_task_critique_reports` row containing at least one
`decision: "accepted"` item still in place (i.e. before the backend's next real upload would
overwrite it).

## 2026-08-13 — Same carry-forward behavior extended to RC & CAPA Critique, backend changes included this time

Per the user, extended the pattern above to `POST /critique/critique-rc-conclusion` and
`POST /critique/critique-capa` (`api/routes/critique_route.py`) — this time *with* the backend
change, since RC & CAPA doesn't have Task Critique's "decisions get wiped on the next upload"
problem in the first place: `investigation_rc_capa_reports` is append-only (one fresh row per
attempt, never overwritten — see `backend/backend/db/rc_capa_critique_queries.py`'s own docstring),
so the previous attempt's `rc_recommendations`/`capa_recommendations` (each already carrying
`decision`) are sitting right there in the row the backend already fetches for state computation.
No DS-side DB query, no history table, no call-order dependency at all — simpler than Task Critique
end to end.

**Backend** (`backend/backend/routers/rc_capa_critique.py`): `upload_rc_capa_report` already calls
`fetch_rc_capa_reports(deviation_id)` up front to compute upload state. Before the DS calls, it now
also walks `reports[-1]["critiques"]` (already fetched, no extra query) to pull `decision ==
"accepted"` descriptions separately per category (`rc_impact` → `previous_rc_recommendations`,
`capa` → `previous_capa_recommendations`), and passes each into `_call_critique_endpoint`, which now
sends `previous_recommendations` (JSON-encoded list) as a third query param alongside the existing
`event_type`/`problem_statement`.

**DS**: `critique-rc-conclusion` and `critique-capa` (and, for consistency, the currently-unused
combined `critique-rc-conclusion-and-capa`) each gained a `previous_recommendations: str = ""`
query param (JSON-encoded list, same shape/parsing as the backend sends). `rc_conclusion_system.txt`
and `capa_system.txt` both gained a "PREVIOUSLY ACCEPTED RECOMMENDATIONS (STILL PENDING)" section
with a `<<<PREVIOUS_RECOMMENDATIONS>>>` sentinel, filled in via a plain `.replace()` (not `.format()`
— both files contain literal `{`/`}` in their own OUTPUT SCHEMA JSON examples, which `.format()`
would choke on) right before use. Same investigator-facing marker as Task Critique,
`"Still unaddressed from the previous review."`, reused verbatim (`UNADDRESSED_MARKER` constant,
duplicated in this file rather than imported from `graph/nodes.py` — the two route modules don't
otherwise share code, and duplicating one string constant seemed cheaper than introducing a
cross-import for it) — kept identical on purpose so the wording is consistent wherever it surfaces.

The two existing post-LLM safety nets got adjusted rather than replaced:
- `_cap_recommendations` (capa) now sorts unaddressed-marker items first before slicing to 5,
  instead of a plain `[:5]` — via a new shared `_prioritize_and_cap` helper.
- `_suppress_recurrence_claims_without_citation` (rc) — which drops any recommendation alleging an
  ignored prior/recurring event unless it cites a concrete deviation reference — now exempts
  marker-prefixed items from that check entirely (they were already vetted on a prior attempt) and
  also routes through `_prioritize_and_cap`. In practice the marker text ("previous review") doesn't
  match `_RECURRENCE_CLAIM_RE`'s noun list anyway, but the explicit exemption removes any risk of a
  wording coincidence silently eating a carried-forward item.

**Verified**: full FastAPI route/OpenAPI registration for all three DS endpoints; every new helper
(`_parse_previous_recommendations`, `_render_previous_recommendations`,
`_with_previous_recommendations`, `_prioritize_and_cap`) directly, including the sentinel
replace against the real prompt files and the recurrence-suppression exemption; the backend's
per-category accepted-recommendation extraction against the real shape of existing
`investigation_rc_capa_reports` rows (both an all-rejected row and a synthetic mixed
accepted/rejected one, matching the real JSON structure confirmed via a direct DB query).

**Not yet live-tested end-to-end against a real LLM call** — the live DB currently has 3 real
`investigation_rc_capa_reports` rows (deviation_id 496712, 500954), but none with any
`decision: "accepted"` recommendation yet (500954's are all `rejected`, 496712's are all still
`pending`) — nothing to exercise the actual carry-forward prompt path against live investigator
decisions yet.

## 2026-08-14 — Live end-to-end test found the "resolved → dropped" path unreliable; fixed by forcing an evidence-grounded verdict before the model writes `recommendations`

Since no real `investigation_rc_capa_reports` row has an accepted recommendation yet, tested
directly against the DS endpoints (`TestClient`, real LLM calls, no backend involved) with
hand-built `.docx` fixtures and fabricated `previous_recommendations` standing in for what the
backend would have extracted. Three scenarios:

1. **Baseline** (no previous recommendations) — correctly no marker, genuine fresh gaps found. Always passed, every run.
2. **Genuinely unaddressed** (unchanged document, re-run with a previously-accepted item still true) — correctly returned again, prefixed with the marker, substance intact. Always passed, every run, across multiple document versions.
3. **Genuinely resolved** (document edited to actually fix the accepted concern) — **failed** repeatedly. Across 4 attempts with progressively more complete/unambiguous fixes — including one isolated case (a CAPA table with an explicit `Responsible Person: John Mathew, Packaging Engineer` cell) where `extract_full_document_text`'s markdown conversion was directly inspected and confirmed clean/correct — the model still re-raised the same accepted item as unresolved, quoting a "missing" fact that was verifiably present in the exact text it was given.

Root-caused as a precision limit in the underlying judgment call, not a data or wiring bug (confirmed by inspecting the actual markdown the model receives — it was correct and unambiguous every time). `is this specific concern resolved?` was being decided implicitly, bundled into the same single pass as the six-dimension fresh gap analysis and the final recommendation write-up, on `gpt-5.4-mini` (`config/settings.py`) at temperature 0 — a small model doing an unscaffolded, high-precision cross-reference task.

**Fix**: added `previous_recommendation_checks: List[PreviousRecommendationCheck]` (`api/schemas.py` — `recommendation`, `resolved: bool`, `evidence: str`) to both `RCConclusionCritiqueResponse` and `CAPACritiqueResponse`, declared *before* `recommendations` in each model — structured-output generation follows field declaration order, so the model is forced to reason through and cite evidence for every previous item before it ever writes the final list. Both prompts now explicitly require: re-read the current document for the literal text that would resolve each item, decide `resolved` only from what's literally present, and require `evidence` to quote/cite that text (or state precisely what's missing) — never a restatement of the original concern. The field is additive-only; the backend/callers already only read `.recommendations`/`.strengths`/`.rc_conclusion_text` and ignore unknown fields, so no downstream change was needed.

**Re-tested all 3 scenarios after the fix**: baseline and genuinely-unaddressed still pass exactly as before (no regression). The previously-failing resolved case — including the isolated CAPA-table one — now correctly returns `resolved: true` with an accurate evidence quote (e.g. citing the exact table row and responsible person) and correctly drops the item from `recommendations` with an empty list. Considered the carry-forward feature validated end-to-end as of this entry, using synthetic documents — still worth a real live run once a real `investigation_rc_capa_reports` row has an accepted recommendation to carry forward.

## 2026-08-14 — Same evidence-grounding fix applied to Task Critique (v7); same result

Task Critique's carry-forward (`critique_task.yaml` v6, `graph/nodes.py`'s `critique_tasks`) has the
identical unscaffolded pattern RC & CAPA had — same bundled single-pass judgment, same
`gpt-5.4-mini` model — and had never been live-tested at all (it's been fully dormant pending the
separate backend change to send `deviation_id`/`task_index`). Applied the same fix pre-emptively
rather than waiting to hit the same bug live:

- `graph/schemas.py`: added `PreviousRecommendationCheck` (duplicated from `api/schemas.py` rather
  than imported — `graph/` and `api/` don't otherwise share schema code, matching the precedent
  already set for `UNADDRESSED_MARKER`) and a `previous_recommendation_checks` field on
  `TaskCritiqueDetail`, declared before `recommendations`.
- `critique_task.yaml`: new `v7` (now active), `v6` kept for history — same
  re-read-and-cite-evidence instructions as the RC/CAPA prompts, adapted to a task's
  findings/inference instead of a full document.

**Tested directly against `critique_tasks`** (calling `parse_document`/`extract_tasks` on a real
hand-built `.docx` for a single investigation task, then invoking `critique_tasks` directly with a
fabricated `previous_recommendations` — bypassing `fetch_previous_recommendations`/the DB entirely,
since this exercises exactly the part that changed):

1. **Baseline** — no marker, genuine gaps found. Passed.
2. **Genuinely unaddressed** (task findings/inference unchanged) — correctly `resolved: false` with
   accurate evidence, regenerated with the marker. Passed.
3. **Resolved** — first attempt added real supporting evidence (a calibration finding) but didn't
   explicitly tie it to the specific batch/defect count; the model correctly kept it open
   (`resolved: false`) with accurate reasoning — a legitimate partial-fix catch, not a hallucination
   like RC/CAPA's failures had been. A second, more complete fix that explicitly closed that link
   was correctly recognized (`resolved: true`, accurate evidence quote, item dropped, empty
   `recommendations`).

No hallucinated "still missing" verdicts reproduced here at all, unlike RC & CAPA's pre-fix
behavior — consistent with the fix generalizing correctly, though also consistent with just not
having hit an unlucky case yet given the smaller number of test runs. Still fully dormant pending
the backend change described above.

## 2026-08-14 — Backend change (deferred above, 2026-08-12 entry) now done: Task Critique's carry-forward is live

Per the user, made the one backend change this feature was waiting on.
`backend/backend/routers/task_critique.py`'s `upload_task_report` now sends `deviation_id` and
`task_index` alongside the existing `problem_statement`/`event_type`/`task_description`/`file` in
its call to `POST /critique/analyse-task-report` — as `data=` (multipart form fields), not
`params=` (query string), since DS declares them via `Form(...)` while the other three are plain
scalars (query params). Mixing both in one httpx call (`params=` + `data=` + `files=`) is valid;
confirmed directly against a stub route mirroring `analyse_task_report`'s exact parameter
declarations that all five fields bind correctly and `deviation_id`/`task_index` arrive as real
`int`s, not strings — no live LLM call needed to verify this, it's a pure wire-format question.

This feature is no longer dormant — every real Task Critique re-upload now exercises
`fetch_previous_recommendations` for real. The invariant flagged in the 2026-08-12 entry (DS reads
`investigation_task_critique_reports`' current row assuming the backend calls DS *before*
overwriting it) still holds — this change didn't touch call order, only added two fields to the
existing call.

**Not yet tested against this exact backend code path end-to-end** (real HTTP request through the
real backend into real DS) — verified in pieces instead: the wire format (above), DS's
`fetch_previous_recommendations` + `critique_tasks` + v7 prompt (2026-08-12/14 entries, direct
graph-level testing including against a real production-style report), and the backend's own
`upsert_report`/`save_critique`/`insert_recommendation_history` call sequence (unchanged, pre-existing
code, not touched by this diff). No local backend `.env` exists in this environment to run the
actual FastAPI server and issue a real request through it.
