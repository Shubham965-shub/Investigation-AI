export type ScoreGrade = {
  text: string;
  bg: string;
  border: string;
};

// 90+ dark green, 80+ light green, 70+ yellow, else red — reuses existing color tokens (--color-primary is a deeper green than --color-success-text) for two green tiers without adding a new token.
export function scoreGrade(score: number): ScoreGrade {
  if (score >= 90) {
    return { text: "var(--color-primary)", bg: "var(--color-rail-active-bg)", border: "var(--color-primary)" };
  }
  if (score >= 80) {
    return { text: "var(--color-success-text)", bg: "var(--color-success-bg)", border: "var(--color-success-text)" };
  }
  if (score >= 70) {
    return { text: "var(--color-warning-text)", bg: "var(--color-warning-bg)", border: "var(--color-warning-text)" };
  }
  return { text: "var(--color-danger-text)", bg: "var(--color-danger-bg)", border: "var(--color-danger-text)" };
}
