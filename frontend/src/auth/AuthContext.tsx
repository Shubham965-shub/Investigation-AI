import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { login as loginRequest } from "../api/auth";

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

  const value = useMemo<AuthContextValue>(
    () => ({
      username,
      isAuthenticated: username !== null,
      login: async (usernameInput: string, password: string) => {
        const response = await loginRequest(usernameInput, password);
        localStorage.setItem("auth_token", response.access_token);
        localStorage.setItem("auth_username", response.username);
        setUsername(response.username);
      },
      logout: () => {
        localStorage.removeItem("auth_token");
        localStorage.removeItem("auth_username");
        setUsername(null);
      },
    }),
    [username]
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
