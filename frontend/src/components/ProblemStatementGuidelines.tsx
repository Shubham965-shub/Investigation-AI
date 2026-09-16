import { InfoTooltip } from "./InfoTooltip";

const POINTS = [
  <>Clearly describe the nature of the <strong>failure or non-conformance</strong> observed (e.g., CQA, parameter, or procedure).</>,
  <>Identify the <strong>stage at which the non-conformance was detected</strong> (e.g., during review, line clearance, analysis, or reporting).</>,
  <>Specify the <strong>product name</strong> involved.</>,
  <>Mention <strong>who identified the non-conformance</strong>, including their role, as applicable.</>,
  <>Compare the <strong>actual result against the specification or standard</strong>.</>,
];

// Content matches the provided guidelines screenshot verbatim, not paraphrased.
export function ProblemStatementGuidelines() {
  return (
    <InfoTooltip label="Problem statement guidelines">
      <p style={{ margin: "0 0 10px", fontWeight: 700, fontSize: "var(--font-size-base)" }}>The problem statement should:</p>
      <ol style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 8 }}>
        {POINTS.map((point, i) => (
          <li key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
            <span
              style={{
                flexShrink: 0,
                width: 18,
                height: 18,
                borderRadius: "50%",
                background: "var(--color-success-bg)",
                color: "var(--color-primary)",
                fontWeight: 700,
                fontSize: "var(--font-size-xs)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {i + 1}
            </span>
            <span>{point}</span>
          </li>
        ))}
      </ol>
    </InfoTooltip>
  );
}