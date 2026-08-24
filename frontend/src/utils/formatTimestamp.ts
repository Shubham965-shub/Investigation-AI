// "Tuesday, 18 Aug 2026, 2:32 PM" (2026-08-18, per the user) — used on
// attempt-history entries (Task Critique's Recommendation History,
// RC & CAPA's history panel) so each past attempt's timestamp reads as
// day + date + time, not just a bare date.
export function formatAttemptTimestamp(iso: string): string {
  const d = new Date(iso);
  const day = d.toLocaleDateString(undefined, { weekday: "long" });
  const date = d.toLocaleDateString(undefined, { day: "2-digit", month: "short", year: "numeric" });
  const time = d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
  return `${day}, ${date}, ${time}`;
}