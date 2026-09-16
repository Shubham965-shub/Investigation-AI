import { Navigate, Outlet, useLocation } from "react-router-dom";
import { AppHeader } from "./AppHeader";
import { useAuth } from "../auth/AuthContext";

export function RootLayout() {
  const { roles } = useAuth();
  const location = useLocation();

  // CXO role only ever sees the CXO Dashboard; redirected here rather than per-route so it applies regardless of how the browser got to any other path.
  if (roles.includes("CXO") && location.pathname !== "/cxo-dashboard") {
    return <Navigate to="/cxo-dashboard" replace />;
  }

  return (
    <div style={{ minHeight: "100vh", width: "100%", display: "flex", flexDirection: "column" }}>
      <AppHeader />
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <main style={{ flex: 1, minWidth: 0, background: "var(--color-bg)", overflowX: "clip" }}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
