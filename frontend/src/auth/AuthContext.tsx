import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { login as loginRequest } from "../api/auth";
import { isTokenExpired } from "./jwt";

interface AuthContextValue {
  username: string | null;
  isAuthenticated: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [username, setUsername] = useState<string | null>(
    () => localStorage.getItem("auth_username")
  );
  // Tracked separately from `username` (not just read from localStorage
  // inline) so logging back in as the SAME username after a prior session's
  // token expired actually triggers a re-render. If only `username` were
  // used as the reactive trigger, `setUsername(response.username)` would be
  // a no-op re-render-wise whenever it's the same string as the current
  // state (React bails out of re-rendering on an unchanged primitive) — so
  // isAuthenticated would never flip to true and the post-login redirect
  // would never fire until a full page reload. The token is virtually
  // guaranteed to differ on every login (fresh iat/exp claims), so it
  // reliably triggers the update even on a repeat login as the same user.
  const [token, setToken] = useState<string | null>(
    () => localStorage.getItem("auth_token")
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      username,
      // A cached username alone isn't enough — the token itself may have
      // expired (or be an old opaque placeholder from before real JWTs)
      // since it was last set, so don't show the user as logged in based on
      // localStorage contents that no longer represent a valid session.
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
    [username, token]
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