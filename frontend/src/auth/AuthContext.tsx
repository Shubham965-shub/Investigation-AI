import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { login as loginRequest } from "../api/auth";
import { isTokenExpired, nameFromToken, rolesFromToken } from "./jwt";
import { posthog, posthogEnabled } from "../telemetry/posthog";

interface AuthContextValue {
  username: string | null;
  // Display name from the token's `name` claim (athena_users.full_name); null until a token exists.
  fullName: string | null;
  // athena_roles.name values (e.g. ["SIT"]); use this rather than hardcoding a username to branch UI by role.
  roles: string[];
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
  // Demo-only: lets the account menu simulate viewing as another investigator via Action Center's filter, without real re-auth. Not persisted.
  viewAsInvestigator: string | null;
  setViewAsInvestigator: (investigator: string | null) => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [username, setUsername] = useState<string | null>(
    () => localStorage.getItem("auth_username")
  );
  // Tracked separately from `username`: re-login as the same username after expiry is a no-op for React's bail-out check, so `token` (always fresh) is what actually triggers the re-render.
  const [token, setToken] = useState<string | null>(
    () => localStorage.getItem("auth_token")
  );
  const [viewAsInvestigator, setViewAsInvestigator] = useState<string | null>(null);

  const fullName = token ? nameFromToken(token) : null;
  const roles = token ? rolesFromToken(token) : [];
  const isAuthenticated = username !== null && token !== null && !isTokenExpired(token);

  // Covers both a fresh login and an already-authenticated page reload (localStorage-restored
  // session) — reactive on isAuthenticated rather than duplicated inside login() directly.
  useEffect(() => {
    if (!posthogEnabled || !isAuthenticated || !username) return;
    // Lowercased: username is email-shaped in this app's data (routers/auth.py's own login is
    // case-insensitive), and PostHog's distinct_id is case-sensitive — without this, the same
    // person logging in with a different case at different times would fork into two PostHog
    // identities. The `email` property (also lowercased) lets this app's person profiles merge
    // with the sibling apps sharing this self-hosted PostHog project, which identify by email.
    const normalizedUsername = username.toLowerCase();

    console.log({normalizedUsername, username});
    
    posthog.identify(normalizedUsername, { name: fullName ?? username, email: normalizedUsername, roles });
    if (roles[0]) posthog.group("role", roles[0], { name: roles[0] });
    // Re-opts in in case a previous logout in this tab opted out (see logout() below) — capture
    // itself stays on by default from boot so pre-login events (loginFailed etc.) keep working;
    // this only re-arms it after a logout, it's not a from-scratch consent gate like CPV's.
    posthog.opt_in_capturing({ captureEventName: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated, username]);

  const value = useMemo<AuthContextValue>(
    () => ({
      username,
      fullName,
      roles,
      viewAsInvestigator,
      setViewAsInvestigator,
      isAuthenticated,
      login: async (usernameInput: string, password: string) => {
        const response = await loginRequest(usernameInput, password);
        localStorage.setItem("auth_token", response.access_token);
        localStorage.setItem("auth_username", response.username);
        setToken(response.access_token);
        setUsername(response.username);
      },
      logout: () => {
        localStorage.removeItem("auth_token");
        localStorage.removeItem("auth_username");
        setToken(null);
        setUsername(null);
        if (posthogEnabled) {
          posthog.reset();
          // Stops tracking this now-signed-out session until the next login re-opts in above.
          posthog.opt_out_capturing();
        }
      },
    }),
    [username, token, viewAsInvestigator]
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}