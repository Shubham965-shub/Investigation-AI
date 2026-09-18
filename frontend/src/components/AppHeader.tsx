import { useState } from "react";
import { useNavigate } from "react-router-dom";
import logo from "../assets/icons/logo.png";
import athenaLogo from "../assets/icons/athena-logo.svg";
import headerIcon1 from "../assets/icons/header-icon-1.svg";
import headerIcon2 from "../assets/icons/header-icon-2.svg";
import userManagementIcon from "../assets/icons/panel-team.svg";
import cxoDashboardIcon from "../assets/icons/cxo-dashboard-icon.svg";
import { useTheme } from "../theme/ThemeContext";
import { useAuth } from "../auth/AuthContext";
import { usePanelState } from "./PanelStateContext";
import { AppFeedbackButton } from "./AppFeedbackButton";

// Temporary demo control — hardcoded to the investigator with the most open investigations; remove once demo need passes.
const DEMO_VIEW_AS_INVESTIGATOR = "Dileep Dasampalli";

// First name in full, every remaining name reduced to its initial; single-word names shown as-is.
function formatShortName(fullName: string): string {
  const parts = fullName.trim().split(/\s+/).filter(Boolean);
  if (parts.length <= 1) return fullName;
  const [first, ...rest] = parts;
  return [first, ...rest.map((p) => p[0]?.toUpperCase())].join(" ");
}

export function AppHeader() {
  const { toggleTheme } = useTheme();
  const { username, fullName, roles, logout, viewAsInvestigator, setViewAsInvestigator } = useAuth();
  const { isPanelOpen } = usePanelState();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header
      style={{
        background: "var(--color-header-bg)",
        borderBottom: "1px solid var(--color-header-border)",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        padding: "20px 32px 21px",
        position: isPanelOpen ? "sticky" : "relative",
        top: isPanelOpen ? 0 : undefined,
        // Below the preview panel's backdrop (zIndex 40) so the backdrop dims the header strip too.
        zIndex: isPanelOpen ? 30 : "auto",
        // position can't be transitioned by CSS; animate the slide instead to match the panel's open transition.
        animation: isPanelOpen ? "app-header-slide-down 250ms ease" : "none",
      }}
    >
      <div
        role="button"
        tabIndex={0}
        onClick={() => navigate("/")}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") navigate("/");
        }}
        style={{ display: "flex", alignItems: "center", gap: 12, cursor: "pointer" }}
      >
        <img src={logo} alt="Strides" style={{ height: 42 }} />
        <span style={{ fontSize: "var(--font-size-xl)", color: "var(--color-primary)" }}>|</span>
        <img src={athenaLogo} alt="" style={{ height: 36 }} />
        <span style={{ fontFamily: "var(--font-heading)", fontWeight: 700, fontSize: "var(--font-size-xl)", color: "#fafafa" }}>
          Athena
        </span>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginRight: 16 }}>
        <AppFeedbackButton />

        {/* Backend re-checks the Admin role independently; hiding the button is just UX, not the real gate. */}
        {roles.includes("Admin") && (
          <button
            type="button"
            aria-label="User Management"
            title="User Management"
            onClick={() => navigate("/user-management")}
            style={{ background: "none", border: "none", width: 40, height: 40, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center" }}
          >
            <img src={userManagementIcon} alt="" width={20} height={20} />
          </button>
        )}

        {/* Same UX-only gate as the Admin button; CxoDashboardPage checks the role itself. */}
        {roles.includes("CXO") && (
          <button
            type="button"
            aria-label="CXO Dashboard"
            title="CXO Dashboard"
            onClick={() => navigate("/cxo-dashboard")}
            style={{ background: "none", border: "none", width: 40, height: 40, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center" }}
          >
            <img src={cxoDashboardIcon} alt="" width={20} height={20} />
          </button>
        )}

        <button
          type="button"
          aria-label="Toggle dark mode"
          onClick={toggleTheme}
          style={{ background: "none", border: "none", width: 40, height: 40, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center" }}
        >
          <img src={headerIcon1} alt="" width={20} height={20} />
        </button>

        {(viewAsInvestigator ?? fullName) && (
          <span style={{ fontSize: "var(--font-size-sm)", fontWeight: 600, color: "#fafafa" }}>
            {formatShortName(viewAsInvestigator ?? fullName!)}
          </span>
        )}

        <div style={{ position: "relative" }}>
          <button
            type="button"
            aria-label="Account menu"
            onClick={() => setMenuOpen((prev) => !prev)}
            style={{ background: "none", border: "none", width: 40, height: 40, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center" }}
          >
            <img src={headerIcon2} alt="" width={20} height={20} />
          </button>

          {menuOpen && (
            <>
              <div
                onClick={() => setMenuOpen(false)}
                style={{ position: "fixed", inset: 0, zIndex: 10 }}
              />
              <div
                style={{
                  position: "absolute",
                  right: 0,
                  top: 48,
                  background: "var(--color-surface)",
                  border: "1px solid var(--color-card-border)",
                  borderRadius: "var(--radius-btn)",
                  boxShadow: "0 10px 15px rgba(0,0,0,0.15)",
                  minWidth: 200,
                  padding: 12,
                  zIndex: 20,
                  display: "flex",
                  flexDirection: "column",
                  gap: 8,
                }}
              >
                <div>
                  <p style={{ margin: 0, fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>Signed in as</p>
                  <p style={{ margin: 0, fontWeight: 700, color: "var(--color-text)" }}>{username}</p>
                  {viewAsInvestigator && (
                    <p style={{ margin: "2px 0 0", fontSize: "var(--font-size-xs)", color: "var(--color-primary)" }}>
                      Viewing dashboard as {viewAsInvestigator}
                    </p>
                  )}
                </div>

                {(roles.includes("Admin") || roles.includes("SIT")) && (
                  <div style={{ borderTop: "1px solid var(--color-card-border)", paddingTop: 8 }}>
                    <label style={{ display: "block", fontSize: "var(--font-size-xs)", color: "var(--color-text-muted)", marginBottom: 4 }}>
                      View dashboard as (demo)
                    </label>
                    <select
                      value={viewAsInvestigator ?? ""}
                      onChange={(e) => {
                        const value = e.target.value || null;
                        setViewAsInvestigator(value);
                        setMenuOpen(false);
                        if (value) navigate("/");
                      }}
                      style={{
                        width: "100%",
                        border: "1px solid var(--color-card-border)",
                        borderRadius: "var(--radius-btn)",
                        padding: "6px 8px",
                        fontSize: "var(--font-size-sm)",
                        background: "var(--color-surface)",
                        color: "var(--color-text)",
                      }}
                    >
                      <option value="">— My account —</option>
                      <option value={DEMO_VIEW_AS_INVESTIGATOR}>{DEMO_VIEW_AS_INVESTIGATOR}</option>
                    </select>
                  </div>
                )}

                <button
                  type="button"
                  onClick={logout}
                  style={{
                    background: "none",
                    border: "1px solid var(--color-card-border)",
                    borderRadius: "var(--radius-btn)",
                    padding: "6px 10px",
                    color: "var(--color-text)",
                    textAlign: "left",
                  }}
                >
                  Log out
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
