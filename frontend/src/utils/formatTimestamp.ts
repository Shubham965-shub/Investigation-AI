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

// "Last updated on 10 Sep 2026 at 14:35" (2026-09-09, per the user) — top-
// right stamp on Action Center/Analytics/SIT Dashboard, sourced from
// fact_qms_event.pg_updated_at_timestamp. 24-hour time, unlike
// formatAttemptTimestamp's 12-hour AM/PM — an explicit, separate format the
// user asked for here, not a reuse of that one.
//
// Explicitly rendered in IST (Asia/Kolkata), not the viewer's own browser/OS
// timezone (2026-09-10, per the user — the raw value is UTC, and this is a
// single-timezone internal tool, so every viewer should see the same
// canonical time regardless of their machine's own timezone setting).
export function formatLastUpdated(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const date = d.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "Asia/Kolkata" });
  const time = d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "Asia/Kolkata" });
  return `Last updated on ${date} at ${time} IST`;
}