import { apiGet, apiPost } from "./client";

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
