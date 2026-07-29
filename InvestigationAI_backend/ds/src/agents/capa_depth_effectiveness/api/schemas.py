import re
from typing import List, Literal
from pydantic import BaseModel, model_validator

# Tokens that, alone or repeated (e.g. "NA NA NA NA NA"), mean the quoted
# effectiveness-plan text carries no actual justifying clause — just a
# placeholder. Anything with extra substantive words (e.g. "Not applicable —
# since no CAPA is recommended") is not bare and is left to the model's own
# Rule 2 judgment.
_BARE_PLACEHOLDER_TOKENS = {
    "na", "n/a", "not", "applicable", "none", "nil", "present", "stated", "required",
}


def _is_bare_placeholder(quote: str) -> bool:
    tokens = re.sub(r"[^\w\s/]", "", quote.strip().lower()).split()
    return not tokens or all(t in _BARE_PLACEHOLDER_TOKENS for t in tokens)


# ---------- Rule-critique primitive ----------
# Intentionally duplicated (not imported) from src.agents.critique.api.schemas —
# this module has no dependency on critique's API contract, only on its
# low-level docx extraction utility (see services/capa_depth_effectiveness_service.py).

class RuleCritique(BaseModel):
    rule_number: int
    rule_name: str
    critique: str  # empty string "" if the rule is fully satisfied


# ---------- CAPA Depth Classification (SOP GQA/070 CAPA Hierarchy) ----------
# A CAPA often bundles multiple distinct actions of DIFFERENT depths (e.g. one
# procedural instruction change + one physical equipment change). Forcing a
# single hierarchy_level across all of them is exactly what caused the
# Level 4 vs Level 5 flip-flopping we observed on 459682_OOT.docx — the model
# was implicitly averaging/picking-one across two actions with genuinely
# different depths depending on which it weighted more heavily on a given run.
# Fix: classify each action independently. No aggregate/overall level is
# computed — that was found to not be part of the requirements, and scoring a
# single "weakest link" number also turned out to silently depend on getting
# action scope exactly right (see the Interim Control / Extrapolation scoping
# rules in the prompt) — dropped rather than kept as a semi-reliable number.

class CAPAActionClassification(BaseModel):
    action_description: str  # this one action, as close to verbatim as possible
    hierarchy_rationale: str  # reasoning FIRST — why this action fits a level, before naming it
    hierarchy_level: int  # 1-5, per GQA/070 Table 2
    hierarchy_level_label: str  # e.g. "Error Prevention"


class CAPADepthClassification(BaseModel):
    product_batch_reference: str
    root_cause_summary: str
    actions: List[CAPAActionClassification]

    @model_validator(mode="after")
    def _at_least_one_action(self):
        if not self.actions:
            raise ValueError(
                "actions must contain at least one CAPA action classification — "
                "if no CAPA is warranted, still include one entry classified as Level 1"
            )
        return self


# ---------- Effectiveness Check Plan (SOP GQA/008) ----------

# Enum-constrained under strict structured outputs: the model cannot emit a
# value outside these lists, and (crucially) generation follows field order,
# so the reasoning fields below are produced BEFORE the verdicts they govern.

MonitoringMethod = Literal[
    "Auditing",
    "Spot Check",
    "Sampling",
    "Monitoring",
    "Trend analysis",
    "Periodic product review",
    "Surprise Audit",
    "Periodic Checks",
    "Verification of Validation Reports",
    "Not clearly classifiable",
]

MonitoringTiming = Literal["prospective", "retrospective", "not stated"]

Rule4Classification = Literal[
    "(a) root-cause targeting",
    "(b) event impact assessment",
    "(c) CAPA rationale",
    "(d) genuine implementation-risk statement",
    "(e) none found",
]


class ExtractionReasoning(BaseModel):
    # Field order matters: quote -> evidence sentence -> timing verdict.
    effectiveness_plan_quote: str  # verbatim plan text, or "not present"
    monitoring_method_timing_evidence: str  # one sentence: will data come from batches AFTER the CAPA, or an existing dataset?
    monitoring_method_timing: MonitoringTiming


class EffectivenessCheckExtraction(BaseModel):
    reasoning: ExtractionReasoning  # MUST be first — generated before the fields below
    kpi: str
    monitoring_method: MonitoringMethod
    time_horizon: str  # verbatim as stated in the report; "" if not stated
    acceptance_criteria: str
    responsible_party: str
    # The CAPA ACTION's own due date (SOP 6.1.2.3), from the CAPA table's "Due
    # Date" column — distinct from time_horizon above, which is the
    # effectiveness-check MONITORING period. Conflating the two is what caused
    # Rule 1 (Time-bound) to fire inconsistently: two reports with an identical
    # real CAPA due date but a blank EC time_horizon got opposite Rule 1
    # verdicts, because Rule 1 had no dedicated field to check and the model
    # was substituting time_horizon as a stand-in. "" only if genuinely no due
    # date is stated (e.g. the column literally reads "NA"/"Not applicable");
    # a vague deferred reference (e.g. "As per change control due date") is
    # preserved verbatim, not converted to "".
    capa_due_date: str

    @model_validator(mode="after")
    def _enforce_timing_consistency(self):
        t = self.reasoning.monitoring_method_timing
        m = self.monitoring_method
        # Deterministic mappings: auto-correct silently (safe, rule is 1:1).
        if t == "prospective" and m != "Monitoring":
            self.monitoring_method = "Monitoring"
        elif t == "not stated" and m != "Not clearly classifiable":
            self.monitoring_method = "Not clearly classifiable"
        # Non-deterministic mapping: retrospective allows two methods — reject
        # anything else so the caller can retry.
        elif t == "retrospective" and m not in ("Trend analysis", "Periodic product review"):
            raise ValueError(
                "retrospective timing requires 'Trend analysis' or "
                f"'Periodic product review', got '{m}'"
            )
        return self

    @model_validator(mode="after")
    def _kpi_not_duplicated(self):
        # Two genuinely empty strings both mean "nothing stated" — that's a
        # legitimate blank EC plan (e.g. the report's own table is just
        # "NA"/"NA"), not the model lazily copying one value into both fields.
        # Only reject when they're equal AND non-empty.
        kpi = self.kpi.strip()
        acceptance = self.acceptance_criteria.strip()
        if kpi and kpi.lower() == acceptance.lower():
            raise ValueError(
                "kpi duplicates acceptance_criteria; kpi must name WHAT is "
                "measured, acceptance_criteria the pass/fail threshold"
            )
        return self


class CritiqueReasoning(BaseModel):
    # Field order matters: quote -> classification.
    rule4_candidate_quote: str  # verbatim closest candidate in the WHOLE report, or "none found"
    rule4_classification: Rule4Classification


# ---------- Generated Effectiveness Plan (SOP-grounded draft, SOP GQA/008) ----------
# Section 12 (the Effectiveness Check Plan table) is present in historical
# reports but, per updated requirements, is not guaranteed to be authored in
# future reports — this section drafts what it SHOULD contain, grounded in
# SOP 6.1.2.1/6.1.2.4/6.1.3.2 and content appearing BEFORE section 12 (root
# cause, CAPA description, trend/risk data), independent of whatever section
# 12 itself actually says.

EffectivenessCategory = Literal[
    "CpK improvement",
    "% Reduction/elimination of errors",
    "Reduction in repeat deviations",
    "Reduction in Human error",
    "Improvement in Key performance indicators (KPIs)",
    "Product consistently meeting newly defined criteria",
    "Improvement in % yield",
    "Reduction in invalidate rate associated with root cause",
    "Improvement in trends",
    "Improvement in Site quality metrics",
    "Other",
]

# Forced discrete commitment for monitoring_duration, mirroring the
# monitoring_method_timing fix: free-form reasoning about risk/engineered-vs-
# procedural was found to NOT reliably move the final duration value — a live
# investigation found ~10 reports across a real spread of cited risk levels
# (Level 2 through Level 4) all converged on the same generic value, because
# the prompt's only worked example and its "no risk data" fallback both used
# the identical phrase, giving the model one strong attractor and no evidence
# duration should ever look different. Forcing a categorical tier BEFORE the
# free-text value — with the tier label itself stating the numeric band —
# gives the model a concrete anchor per risk level instead of one shared one.
DurationTier = Literal[
    "short (3-5 batches, ~30 days) — high risk + engineered fix + high detection probability",
    "standard (5-8 batches, ~45-60 days) — moderate risk, or a mix of engineered and procedural elements",
    "extended (8-10 batches, ~60-90 days) — low risk, a procedural/training-based fix, or no risk data to calibrate against",
    "not applicable — no CAPA action exists in this report to monitor",
]

# Gates the whole plan on whether a genuine CAPA action exists at all — an
# empirical study across all 50 historical reports found ~14 of them have NO
# CAPA whatsoever (root cause unassignable, or existing controls judged
# adequate), yet generated_plan had no way to detect this and would draft a
# full plan (including a fabricated duration) regardless. This is checked
# ONLY for "does a CAPA action exist" — NOT for whether the report's OWN
# section 12 chose to waive its effectiveness check (a real CAPA with a
# waived EC still gets a full generated plan; only the absence of any CAPA
# makes the plan "not applicable").
CAPAApplicability = Literal[
    "yes — a CAPA action is proposed in this report",
    "no — the report explicitly states no CAPA is warranted or proposed",
]


class EffectivenessPlanGrounding(BaseModel):
    # Reasoning FIRST: locate real preceding evidence before drafting the plan,
    # so criteria reference facts already in the report rather than invented
    # numbers (same reasoning-before-verdict pattern used elsewhere here).
    root_cause_basis: str  # one sentence recapping the failure mode the check needs to verify is resolved
    preceding_evidence_quote: str  # verbatim quote from EARLIER in the report (never section 12) with a quantitative baseline (CpK, defect rate, trend, yield); "not available" if genuinely none exists
    sop_category: EffectivenessCategory  # nearest fitting SOP 6.1.3.2 typical example


class EffectivenessCheckRuleCritiques(BaseModel):
    # No improvement_suggestions field — dropped; it was never part of the
    # stated requirements (SOP, alignment emails, or an explicit ask), just an
    # ad-hoc addition to hold advisory-checklist observations. Advisory items
    # (SOP 6.1.2.4's other bullets, 6.1.3.3's 8-question checklist) are now
    # simply not surfaced at all — not scored, not noted anywhere.
    reasoning: CritiqueReasoning  # MUST be first — generated before the critiques
    rule_critiques: List[RuleCritique]  # always exactly 4 entries, fixed order
    overall_assessment: str

    @model_validator(mode="after")
    def _exactly_four_in_order(self):
        if [rc.rule_number for rc in self.rule_critiques] != [1, 2, 3, 4]:
            raise ValueError("rule_critiques must be exactly rules 1-4 in order")
        return self

    @model_validator(mode="after")
    def _rule4_consistency(self):
        rule4 = self.rule_critiques[3]
        cls = self.reasoning.rule4_classification
        if cls != "(d) genuine implementation-risk statement" and not rule4.critique.strip():
            raise ValueError(
                f"rule4_classification is '{cls}' but Rule 4 critique is empty; "
                "only classification (d) permits an empty Rule 4 critique"
            )
        if cls == "(d) genuine implementation-risk statement" and rule4.critique.strip():
            raise ValueError(
                "rule4_classification is (d) but Rule 4 critique is non-empty"
            )
        return self


class GeneratedEffectivenessPlan(BaseModel):
    # Reasoning FIRST: does a genuine CAPA action even exist? Only "no CAPA
    # at all" makes the plan not applicable — a CAPA whose own report waived
    # its effectiveness check still gets a full generated plan below.
    applicability_reason: str  # cites the evidence either way, e.g. quotes "no CAPA warranted" or names the actual CAPA action found
    applicable: CAPAApplicability
    grounding: EffectivenessPlanGrounding  # MUST be generated before the fields below
    capa_description: str  # restated from the CAPA action(s) in section 11
    effectiveness_check: str  # the monitoring/verification ACTIVITY to be performed
    effectiveness_criteria: str  # pass/fail criteria — anchored to grounding.preceding_evidence_quote where one exists
    responsibility: str  # who performs the check — "QA" by default per SOP 6.1.3.1 unless the report states otherwise
    # Calibrated per SOP GQA/008 Table 4 (advisory "should" text, not a "shall"
    # rule — there is no formula tying event severity to an exact number):
    # higher risk + an engineered/design fix + high detection probability
    # warrants a shorter duration/fewer batches; a procedural/detection-based
    # fix or lower risk warrants longer/more. This is a reasoned estimate, not
    # an SOP-derived fact. Field order: duration_rationale (open reasoning)
    # -> duration_tier (forced discrete commitment, see DurationTier) ->
    # monitoring_duration (specific value, should fall within the tier's band).
    duration_rationale: str
    duration_tier: DurationTier
    # States BOTH a batch count and a day count from duration_tier's band, e.g.
    # "5 batches or 45 days, whichever is earlier" — never batches alone. Real
    # historical reports overwhelmingly phrase this as batches-only (4 of 6
    # duration mentions found across the 50-report set), but the day-based
    # ceiling exists as a safeguard against slow/low-frequency production,
    # where a pure batch count could translate to an unreasonably long
    # real-world wait — matches the one clear historical precedent for this
    # compound phrasing (459682_OOT.docx: "90 days or 10 batches whichever is
    # earlier"). Earlier prompt/schema comments only ever showed a batches-only
    # example, which is why every live-tested report returned batches alone
    # despite the tier itself already stating a day range.
    monitoring_duration: str

    @model_validator(mode="after")
    def _not_applicable_consistency(self):
        if self.applicable.startswith("no"):
            populated = [
                name
                for name in (
                    "capa_description",
                    "effectiveness_check",
                    "effectiveness_criteria",
                    "responsibility",
                    "duration_rationale",
                    "monitoring_duration",
                )
                if getattr(self, name).strip()
            ]
            if populated:
                raise ValueError(
                    "applicable is 'no' (no CAPA proposed) but these fields are "
                    f"non-empty: {populated}; when no CAPA exists there is nothing "
                    "to draft an effectiveness plan for, so all of them must be "
                    "empty strings"
                )
            if not self.duration_tier.startswith("not applicable"):
                raise ValueError(
                    "applicable is 'no' but duration_tier is not the 'not "
                    "applicable' option — must be consistent"
                )
        return self


class EffectivenessCheckExtractionAndCritique(BaseModel):
    # This is the structured-output schema for the extraction+critique LLM
    # call specifically — it reads the FULL report (section 12 included) and
    # produces `extraction`/`rule_critiques` only. `generated_plan` is
    # produced by a SEPARATE call reading a section-12-REDACTED copy of the
    # report (see strip_section_12 in capa_depth_effectiveness_service.py) —
    # not by this call — because prompt instructions alone ("don't copy
    # section 12") proved insufficient: a live investigation found the
    # generated duration consistently echoing the report's real value,
    # because this call had already written that same real value into
    # `extraction` moments earlier in its own output. Physical separation
    # (two calls, two different texts) is the only reliable fix.
    extraction: EffectivenessCheckExtraction
    rule_critiques: EffectivenessCheckRuleCritiques

    @model_validator(mode="after")
    def _rule3_not_applicable_when_no_plan(self):
        # Rule 2 fails ONLY when neither a plan nor a rationale exists at all
        # (see its own critique instruction) — in that case Rule 3 (sufficiency
        # of data points WITHIN a plan) has nothing to evaluate, so it can never
        # independently fail alongside Rule 2. This is a 1:1-computable
        # relationship (unlike Rule 1 below), so auto-correct silently rather
        # than reject-and-retry.
        rule2 = self.rule_critiques.rule_critiques[1]
        rule3 = self.rule_critiques.rule_critiques[2]
        if rule2.critique.strip() and rule3.critique.strip():
            rule3.critique = ""
        return self

    @model_validator(mode="after")
    def _rule1_due_date_consistency(self):
        # capa_due_date blank (or a bare placeholder like "Not applicable" the
        # model wrote literally despite being told to use "") means the report
        # states no due date at all for the CAPA action — SOP 6.1.2.3 requires
        # one, so that alone fails the Time-bound dimension of Rule 1. Multiple
        # valid critique wordings are possible, so reject-and-retry rather than
        # silently writing one in.
        due_date = self.extraction.capa_due_date
        rule1 = self.rule_critiques.rule_critiques[0]
        if _is_bare_placeholder(due_date) and not rule1.critique.strip():
            raise ValueError(
                "capa_due_date is blank/a bare placeholder (no due date stated "
                "for the CAPA action) but Rule 1 (SMART CAPA Plan) critique is "
                "empty; a CAPA action with no due date fails the Time-bound "
                "dimension and Rule 1 must be flagged"
            )
        return self

    @model_validator(mode="after")
    def _rule2_bare_placeholder_consistency(self):
        # A bare "NA"/"Not applicable" placeholder with no justifying clause is
        # not a rationale (SOP 6.1.2.4 requires one to be "provided") — Rule 2
        # must fail in that case. Reject-and-retry since multiple valid
        # critique wordings are possible. This was observed live: the prompt
        # alone told the model to require a real justifying clause, but it
        # still passed Rule 2 on a bare "Not applicable" quote with no
        # rationale attached (HIGH SCORING 1.docx) — prompting alone wasn't
        # reliable enough, same lesson as Rule 1 above.
        quote = self.extraction.reasoning.effectiveness_plan_quote
        rule2 = self.rule_critiques.rule_critiques[1]
        if _is_bare_placeholder(quote) and not rule2.critique.strip():
            raise ValueError(
                "effectiveness_plan_quote is a bare placeholder with no "
                "justifying clause, but Rule 2 (Effectiveness Plan Identified "
                "or Rationale Given) critique is empty; a bare 'NA'/'Not "
                "applicable' is not a rationale and Rule 2 must be flagged"
            )
        return self


class EffectivenessCheckResult(BaseModel):
    # Plain combining container — assembled by the route from two independent
    # LLM calls (EffectivenessCheckExtractionAndCritique + GeneratedEffectivenessPlan),
    # not itself passed as a structured-output `structure=` schema. No validators
    # here: the cross-field consistency checks already ran when
    # EffectivenessCheckExtractionAndCritique was constructed.
    extraction: EffectivenessCheckExtraction
    rule_critiques: EffectivenessCheckRuleCritiques
    generated_plan: GeneratedEffectivenessPlan


# ---------- Combined response ----------

class CAPADepthEffectivenessResponse(BaseModel):
    event_type: str
    capa_depth: CAPADepthClassification
    effectiveness_check: EffectivenessCheckResult

    def without_reasoning(self) -> dict:
        """Dump for downstream consumers that predate the reasoning fields."""
        d = self.model_dump()
        d["effectiveness_check"]["extraction"].pop("reasoning", None)
        d["effectiveness_check"]["rule_critiques"].pop("reasoning", None)
        return d