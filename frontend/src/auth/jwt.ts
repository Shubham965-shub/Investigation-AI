/** Decodes a base64url string (JWT segments use base64URL — `-`/`_` instead
 * of `+`/`/`, and no padding) — plain atob() throws on those characters,
 * which happens whenever the underlying bytes happen to produce one, i.e.
 * unpredictably per-token, not something a fixed test token would catch. */
function base64UrlDecode(segment: string): string {
  const base64 = segment.replace(/-/g, "+").replace(/_/g, "/").padEnd(segment.length + ((4 - (segment.length % 4)) % 4), "=");
  return atob(base64);
}

/** Client-side JWT expiry inspection — no signature verification (that's the
 * backend's job), purely so a stale/expired/malformed token in localStorage
 * doesn't show the user as authenticated before their first API call.
 * Treats anything that can't be decoded (including the old opaque
 * placeholder tokens some browsers may still have cached) as expired. */
export function isTokenExpired(token: string): boolean {
  try {
    const payload = JSON.parse(base64UrlDecode(token.split(".")[1]));
    if (typeof payload.exp !== "number") return true;
    return payload.exp * 1000 < Date.now();
  } catch {
    return true;
  }
}

/** Pulls the display name embedded in the token's `name` claim (see
 * backend/backend/routers/auth.py's issue_token — athena_users.full_name, or
 * a username-derived fallback) — client-side only, same no-verification
 * caveat as isTokenExpired above. Used by AppHeader to show the signed-in
 * user's name (2026-08-18, per the user) without a separate /auth/me round
 * trip, since it's already right here in the token. */
export function nameFromToken(token: string): string | null {
  try {
    const payload = JSON.parse(base64UrlDecode(token.split(".")[1]));
    return typeof payload.name === "string" && payload.name ? payload.name : null;
  } catch {
    return null;
  }
}

/** Pulls the `roles` claim (see backend/backend/routers/auth.py's
 * issue_token — athena_users.role_id -> athena_roles.name, e.g. "Admin",
 * "User", "SIT") — same no-verification caveat as isTokenExpired above.
 * Used to branch UI on role (e.g. Action Center's "SIT View" label) instead
 * of hardcoding a specific user's identity. */
export function rolesFromToken(token: string): string[] {
  try {
    const payload = JSON.parse(base64UrlDecode(token.split(".")[1]));
    return Array.isArray(payload.roles) ? payload.roles.filter((r: unknown) => typeof r === "string") : [];
  } catch {
    return [];
  }
}