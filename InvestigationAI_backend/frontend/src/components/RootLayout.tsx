import { Outlet } from "react-router-dom";
import { AppHeader } from "./AppHeader";
import { IconRail } from "./IconRail";

export function RootLayout() {
  return (
    <div style={{ minHeight: "100vh", width: "100%", display: "flex", flexDirection: "column" }}>
      <AppHeader />
      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <IconRail />
        <main style={{ flex: 1, minWidth: 0, background: "var(--color-bg)", overflowX: "clip" }}>
          <Outlet />
        </main>
      </div>
    </div>
  );
}
