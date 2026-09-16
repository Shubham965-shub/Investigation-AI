// JWT segments use base64URL (`-`/`_`, no padding); plain atob() throws on those chars, so convert to standard base64 first.
function base64UrlDecode(segment: string): string {
  const base64 = segment.replace(/-/g, "+").replace(/_/g, "/").padEnd(segment.length + ((4 - (segment.length % 4)) % 4), "=");
  return atob(base64);
}

// Client-side expiry check only, no signature verification (that's the backend's job); anything undecodable counts as expired.
export function isTokenExpired(token: string): boolean {
  try {
    const payload = JSON.parse(base64UrlDecode(token.split(".")[1]));
    if (typeof payload.exp !== "number") return true;
    return payload.exp * 1000 < Date.now();
  } catch {
    return true;
  }
}

// Reads the `name` claim (athena_users.full_name) so AppHeader can show it without a separate /auth/me round trip.
export function nameFromToken(token: string): string | null {
  try {
    const payload = JSON.parse(base64UrlDecode(token.split(".")[1]));
    return typeof payload.name === "string" && payload.name ? payload.name : null;
  } catch {
    return null;
  }
}

// Reads the `roles` claim (athena_roles.name, e.g. "Admin"/"SIT") so UI can branch on role instead of a hardcoded username.
export function rolesFromToken(token: string): string[] {
  try {
    const payload = JSON.parse(base64UrlDecode(token.split(".")[1]));
    return Array.isArray(payload.roles) ? payload.roles.filter((r: unknown) => typeof r === "string") : [];
  } catch {
    return [];
  }
}