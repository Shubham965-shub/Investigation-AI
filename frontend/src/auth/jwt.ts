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