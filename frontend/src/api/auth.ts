import { apiGet, apiPost, apiPut } from "./client";

export interface LoginResponse {
  access_token: string;
  token_type: string;
  username: string;
}

export function login(username: string, password: string): Promise<LoginResponse> {
  return apiPost<LoginResponse>("/auth/login", { username, password });
}

export interface PublicStatsResponse {
  open_investigations: number;
}

// Unauthenticated — for the login page's "N investigations · live" stat, shown before a token exists.
export function getPublicStats(): Promise<PublicStatsResponse> {
  return apiGet<PublicStatsResponse>("/public-stats");
}

export interface EventExplorerHandoffResponse {
  url: string;
}

// Mints a short-lived SSO handoff token so "Explore Events" lands the user in Event Explorer (InvestigationAI_FE) already authenticated.
export function getEventExplorerHandoffUrl(): Promise<EventExplorerHandoffResponse> {
  return apiGet<EventExplorerHandoffResponse>("/auth/event-explorer-handoff");
}

// Admin-only: backend enforces 403 for non-Admin tokens (require_admin); the frontend route guard is just a UX nicety on top.
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

// Self-service, any authenticated user — backend re-verifies current_password server-side.
export function changePassword(request: { current_password: string; new_password: string }): Promise<{ status: string }> {
  return apiPut<{ status: string }>("/auth/change-password", request);
}

// Admin-only: backend enforces 403 for non-Admin tokens (require_admin), no current_password needed.
export function adminSetUserPassword(userId: number, newPassword: string): Promise<{ status: string }> {
  return apiPut<{ status: string }>(`/auth/admin/users/${userId}/password`, { new_password: newPassword });
}
