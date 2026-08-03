/** Client-side JWT expiry inspection — no signature verification (that's the
 * backend's job), purely so a stale/expired/malformed token in localStorage
 * doesn't show the user as authenticated before their first API call.
 * Treats anything that can't be decoded (including the old opaque
 * placeholder tokens some browsers may still have cached) as expired. */
export function isTokenExpired(token: string): boolean {
  try {
    const payload = JSON.parse(atob(token.split(".")[1]));
    if (typeof payload.exp !== "number") return true;
    return payload.exp * 1000 < Date.now();
  } catch {
    return true;
  }
}