import { Navigate, Outlet, useLocation } from "react-router-dom";
import { AppHeader } from "./AppHeader";
import { useAuth } from "../auth/AuthContext";

export function RootLayout() {
  const { roles } = useAuth();
  const location = useLocation();

  // CXO role only ever sees the CXO Dashboard (2026-09-09, per the user) —
  // no Action Center, no other page. Redirected here rather than per-route,
  // so it applies uniformly regardless of how a CXO user's browser got to
  // any other path (a stale bookmark, back/forward, a typed URL, or just
  // the app's own default "/" landing).
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
