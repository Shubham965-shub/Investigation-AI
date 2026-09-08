import { apiGet, apiPost, apiPut } from "./client";

export interface LoginResponse {
  access_token: string;
  token_type: string;
  username: string;
}

export function login(username: string, password: string): Promise<LoginResponse> {
  return apiPost<LoginResponse>("/auth/login", { username, password });
}

export interface EventExplorerHandoffResponse {
  url: string;
}

// Mints a short-lived SSO handoff token and returns the full Event Explorer
// URL (InvestigationAI_FE) with it attached — lets "Explore Events" land the
// user there already authenticated (2026-08-19, per the user).
export function getEventExplorerHandoffUrl(): Promise<EventExplorerHandoffResponse> {
  return apiGet<EventExplorerHandoffResponse>("/auth/event-explorer-handoff");
}

// User Management (admin-only, 2026-09-08, per the user) — every call here
// 403s server-side for a non-Admin token (backend/backend/routers/auth.py's
// require_admin), the frontend route guard is just a UX nicety on top.
export interface AdminUserRow {
  id: number;
  username: string;
  full_name: string | null;
  role: string | null;
  is_active: boolean;
  created_at: string;
  last_login: string | null;
}

export interface AdminUserListResponse {
  users: AdminUserRow[];
  roles: string[];
}

export function getAdminUsers(): Promise<AdminUserListResponse> {
  return apiGet<AdminUserListResponse>("/auth/admin/users");
}

export function createAdminUser(request: {
  username: string;
  full_name: string;
  password: string;
  role: string;
}): Promise<AdminUserRow> {
  return apiPost<AdminUserRow>("/auth/admin/users", request);
}

export function updateAdminUserRole(userId: number, role: string): Promise<AdminUserRow> {
  return apiPut<AdminUserRow>(`/auth/admin/users/${userId}/role`, { role });
}
