import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { login as loginRequest } from "../api/auth";
import { isTokenExpired, nameFromToken, rolesFromToken } from "./jwt";

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

  const value = useMemo<AuthContextValue>(
    () => ({
      username,
      fullName: token ? nameFromToken(token) : null,
      roles: token ? rolesFromToken(token) : [],
      viewAsInvestigator,
      setViewAsInvestigator,
      // A cached username alone isn't enough — the token may have expired since it was stored.
      isAuthenticated: username !== null && token !== null && !isTokenExpired(token),
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