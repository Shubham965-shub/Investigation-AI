import { InfoTooltip } from "./InfoTooltip";

const RC_RULES: { label: string; text: string }[] = [
  {
    label: "Evidence-Based Substantiation:",
    text: 'The root cause should be backed by objective evidence generated during the investigation, not assumptions or "most likely" guesses — every cause statement should trace directly to a specific finding, such as a test result, document review, interview, or data trend.',
  },
  {
    label: "Logical Traceability and Linkage:",
    text: "There should be a clear, unbroken chain of reasoning connecting Problem Statement → Investigation Tasks → Findings → Analysis → Root Cause.",
  },
  {
    label: "Historical and Recurrence Assessment:",
    text: "The root cause evaluation should consider the history of similar events — prior deviations, investigations, and their previously identified root causes.",
  },
  {
    label: "Root Cause and Impact Linkage:",
    text: 'The assessed impact on affected batches, other/marketed batches, and area/process/equipment should be a direct, logical consequence of the established root cause, justified by rationale and evidence rather than a generic "no impact" statement.',
  },
];

const CAPA_RULES: { label: string; text: string }[] = [
  {
    label: "Root Cause Alignment:",
    text: "The CAPA should directly address each identified root cause, with no proposed action left unlinked to a confirmed cause.",
  },
  {
    label: "Consistency with Problem and Findings:",
    text: "The CAPA should be consistent with the problem statement and investigation findings, contradicting nothing established during the investigation.",
  },
  {
    label: "Corrective and Preventive Completeness:",
    text: "The CAPA should include both immediate corrective measures to fix the current issue and systemic preventive measures to stop recurrence.",
  },
  {
    label: "Gap and Linkage Integrity:",
    text: "Any gaps, inconsistencies, or weak linkages across inferences, root cause, and CAPA should be identified and clearly highlighted rather than overlooked.",
  },
];

function RuleList({ title, rules }: { title: string; rules: { label: string; text: string }[] }) {
  return (
    <div>
      <p style={{ margin: "0 0 8px", fontWeight: 700, fontSize: "var(--font-size-base)" }}>{title}</p>
      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        {rules.map((rule) => (
          <p key={rule.label} style={{ margin: 0 }}>
            <strong>{rule.label}</strong> {rule.text}
          </p>
        ))}
      </div>
    </div>
  );
}

export function RcConclusionGuidelines() {
  return (
    <InfoTooltip label="RC conclusion guidelines" width={460}>
      <RuleList title="Rules for RC (Root Cause) Conclusion" rules={RC_RULES} />
    </InfoTooltip>
  );
}

export function CapaProposalGuidelines() {
  return (
    <InfoTooltip label="CAPA proposal guidelines" width={460}>
      <RuleList title="Rules for CAPA Proposal" rules={CAPA_RULES} />
    </InfoTooltip>
  );
}