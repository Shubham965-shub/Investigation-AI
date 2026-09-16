// e.g. "Tuesday, 18 Aug 2026, 2:32 PM" — used on attempt-history entries so timestamps read as day + date + time, not just a bare date.
export function formatAttemptTimestamp(iso: string): string {
  const d = new Date(iso);
  const day = d.toLocaleDateString(undefined, { weekday: "long" });
  const date = d.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
  const time = d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  return `${day}, ${date}, ${time}`;
}

// Always rendered in IST (Asia/Kolkata), not the viewer's browser timezone — raw value is UTC and this is a single-timezone internal tool, so every viewer sees the same canonical time.
export function formatLastUpdated(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const date = d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "Asia/Kolkata" });
  const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Kolkata" });
  return `Last updated on ${date} at ${time} IST`;
}