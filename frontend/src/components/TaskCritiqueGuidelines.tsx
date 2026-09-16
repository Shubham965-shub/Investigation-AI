import { InfoTooltip } from "./InfoTooltip";

const DIMENSIONS: { title: string; points: string[] }[] = [
  {
    title: "Adequacy",
    points: [
      "The report should address all investigation objectives, questions, and hypotheses.",
      "All required datasets, observations, and evidence should be included.",
      "Methods, tools, and procedures should be clearly explained and reproducible.",
      "Supporting materials (attachments, logs, references) should be provided.",
    ],
  },
  {
    title: "Accuracy",
    points: [
      "Key facts, data points, and findings should be verified against reliable sources or evidence.",
      "Numbers, statements, and conclusions should be consistent across sections.",
      "Calculation errors, incorrect assumptions, or misinterpretations of data should not be present.",
      "All references should come from reliable, traceable, and relevant sources.",
    ],
  },
  {
    title: "Relevance",
    points: [
      "Every section should directly contribute to the investigation objective.",
      "Findings should be meaningful to decision-makers or intended users.",
    ],
  },
  {
    title: "Scientific Rationale",
    points: [
      "The chosen methods should be appropriate for the problem.",
      "Conclusions should be supported by data, not assumptions.",
      "The report should not incorrectly infer causation from correlation.",
    ],
  },
  {
    title: "Logical Conclusion",
    points: [
      "Conclusions should be directly traceable back to findings and evidence.",
      "Conclusions should avoid unsupported extrapolations beyond available data.",
      "Conclusions should be clearly stated, concise, and unambiguous.",
      "Conclusions should lead to practical recommendations or decisions.",
    ],
  },
  {
    title: "Gap Identification",
    points: [
      "Absent or incomplete datasets should be highlighted.",
      "Unstated or weak assumptions should be identified.",
      "Other plausible explanations should be considered.",
      "Limitations and uncertainties should be explicitly discussed.",
    ],
  },
];

// The 6 rubric dimensions ds's task-report critique grades against.
export function TaskCritiqueGuidelines() {
  return (
    <InfoTooltip label="Task critique guidelines" width={460}>
      <p style={{ margin: "0 0 12px", fontWeight: 700, fontSize: "var(--font-size-base)" }}>
        A well-written task report should satisfy:
      </p>
      <div style={{ display: "flex", flexDirection: "column" }}>
        {DIMENSIONS.map((dim, i) => (
          <div
            key={dim.title}
            style={{
              padding: "10px 0",
              borderTop: i === 0 ? "none" : "1px solid var(--color-card-border)",
            }}
          >
            <p
              style={{
                margin: "0 0 6px",
                display: "inline-block",
                fontWeight: 700,
                fontSize: "var(--font-size-xs)",
                letterSpacing: "0.04em",
                textTransform: "uppercase",
                color: "var(--color-primary)",
                background: "var(--color-success-bg)",
                borderRadius: 4,
                padding: "3px 8px",
              }}
            >
              {dim.title}
            </p>
            <ul style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column", gap: 5 }}>
              {dim.points.map((point) => (
                <li key={point} style={{ display: "flex", gap: 8, alignItems: "flex-start" }}>
                  <span style={{ color: "var(--color-primary)", lineHeight: "1.55em" }}>•</span>
                  <span>{point}</span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </InfoTooltip>
  );
}