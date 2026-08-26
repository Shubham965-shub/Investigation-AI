import { InfoTooltip } from "./InfoTooltip";

const DEVIATION_RULES: { label: string; text: string }[] = [
  {
    label: "Critical Deviation:",
    text: "When the deviation affects the quality attribute or critical process parameter of product, an equipment or instrument critical for process or control, of which the impact to patients (or personnel or environment) is highly probable, and/or indicate serious non-conformance to Marketing authorization/manufacturing authorization, and/or indicate serious safety hazard and/or are in violation of companies Data Integrity Policy.",
  },
  {
    label: "Major Deviation:",
    text: "When the deviation affects the quality attribute or critical process parameter of product, an equipment or instrument critical for process or control, of which the impact to patients (or personnel/environment) is unlikely.",
  },
  {
    label: "Minor Deviation:",
    text: "When the deviation does not affect any quality attribute, a critical process parameter, or an equipment or instrument critical for process or control.",
  },
];

const MARKET_COMPLAINT_RULES: { label: string; text: string }[] = [
  {
    label: "Critical:",
    text: "A complaint in which usage of the product has allegedly resulted / likely to result in a potentially life-threatening event or death or could cause serious irreversible risk to health or permanent impairment of body function, or failure to meet specification as per regulatory authorization, or mix up or contamination of product (Microbiological or with other product).",
  },
  {
    label: "Major:",
    text: "A complaint in which usage of the product has allegedly resulted / likely to result in a reversible risk to health of the patient or illness or mistreatment but not to a life-threatening extent.",
  },
  {
    label: "Minor:",
    text: "Complaints in which the use of or exposure to the said product is not likely to pose a significant hazard to health but may cause some dissatisfaction with respect to quality, quantity, packaging, presentation of a drug product.",
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

// Next to the All/Critical/Major & Minor criticality filter toggle in
// ActionCenterPage.tsx (2026-08-24, per the user). Only shows a definition
// set once a specific event type is picked from the top-level Deviation/
// OOS/OOT/Market Complaint filter pills (2026-08-25, per the user) — no
// defined criticality tiers exist for OOS/OOT, and showing both
// Deviation/Market Complaint definitions together when nothing (or an
// unrelated type) is selected was ambiguous about which applied.
export function CriticalityGuidelines({ eventType }: { eventType: string | null }) {
  const rules = eventType === "Deviation" ? DEVIATION_RULES : eventType === "Market Complaint" ? MARKET_COMPLAINT_RULES : null;
  if (!rules) return null;
  return (
    <InfoTooltip label="Criticality definitions" width={480}>
      <RuleList title={eventType === "Deviation" ? "For Deviations" : "For Market Complaint"} rules={rules} />
    </InfoTooltip>
  );
}
