const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000/api";

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.status = status;
    this.detail = detail;
  }
}

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem("auth_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/** Sliding-expiry refresh — every request made with a still-valid token
 * gets a freshly re-issued one back (new full expiry window) via this
 * header, so an active session keeps extending instead of hard-expiring a
 * fixed time after login regardless of activity. Must run on every
 * request/response, ok or not. */
function applyRefreshedToken(response: Response): void {
  const refreshed = response.headers.get("X-Refreshed-Token");
  if (refreshed) localStorage.setItem("auth_token", refreshed);
}

/** Shared by request<T>() and apiGetBlob() — on a 401 (missing/invalid/
 * expired token), the session is unrecoverable, so clear it and force a
 * fresh login instead of leaving the app stuck showing stale authenticated
 * UI. A full reload (not SPA navigate()) is deliberate: this is a plain
 * module with no router access, and a reload also clears any in-memory
 * state that assumed a valid session. */
async function handleErrorResponse(response: Response): Promise<never> {
  if (response.status === 401) {
    localStorage.removeItem("auth_token");
    localStorage.removeItem("auth_username");
    if (window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
  }
  let detail: unknown;
  try {
    detail = (await response.json()).detail;
  } catch {
    detail = response.statusText;
  }
  throw new ApiError(response.status, detail);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...authHeaders(),
      ...init?.headers,
    },
  });
  applyRefreshedToken(response);

  if (!response.ok) {
    await handleErrorResponse(response);
  }

  // 204 No Content has no body — calling .json() on it throws.
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export function apiPost<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "POST", body: JSON.stringify(body) });
}

export function apiPut<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, { method: "PUT", body: JSON.stringify(body) });
}

export function apiPostForm<T>(path: string, formData: FormData): Promise<T> {
  return request<T>(path, { method: "POST", body: formData });
}

export function apiGet<T>(path: string): Promise<T> {
  return request<T>(path, { method: "GET" });
}

/** For binary downloads (e.g. the RCI Plan .docx export) — bypasses
 * request<T>'s .json() parsing, which would throw on a real file body. */
export async function apiGetBlob(path: string): Promise<Blob> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: "GET",
    headers: authHeaders(),
  });
  applyRefreshedToken(response);
  if (!response.ok) {
    await handleErrorResponse(response);
  }
  return response.blob();
}
