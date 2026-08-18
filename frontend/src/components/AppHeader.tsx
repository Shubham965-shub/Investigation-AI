import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import logo from "../assets/icons/logo.png";
import athenaLogo from "../assets/icons/athena-logo.svg";
import headerIcon1 from "../assets/icons/header-icon-1.svg";
import headerIcon2 from "../assets/icons/header-icon-2.svg";
import headerIconInfo from "../assets/icons/header-icon-info.svg";
import { useTheme } from "../theme/ThemeContext";
import { useAuth } from "../auth/AuthContext";
import { usePanelState } from "./PanelStateContext";
import { InvestigationStatusInfo } from "./InvestigationStatusInfo";
import { AppFeedbackButton } from "./AppFeedbackButton";

// Temporary demo control (2026-08-14, per the user) — the real investigator
// with the most currently open investigations (excluding unassigned rows),
// found via a one-off live-DB query: 19 open investigations, next-highest
// was 14. Hardcoded rather than fetched, since this dropdown is meant to be
// removed once the demo need has passed.
const DEMO_VIEW_AS_INVESTIGATOR = "Veena N Chavan";

// "Ajay Pathania" -> "Ajay P", "Ajay Kumar Pathania" -> "Ajay K P" (2026-08-18,
// per the user) — first name in full, every remaining name reduced to its
// initial. A single-word name (no last name on file) is shown as-is.
function formatShortName(fullName: string): string {
  const parts = fullName.trim().split(/\s+/).filter(Boolean);
  if (parts.length <= 1) return fullName;
  const [first, ...rest] = parts;
  return [first, ...rest.map((p) => p[0]?.toUpperCase())].join(" ");
}

export function AppHeader() {
  const { toggleTheme } = useTheme();
  const { username, fullName, logout, viewAsInvestigator, setViewAsInvestigator } = useAuth();
  const { isPanelOpen } = usePanelState();
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const [infoOpen, setInfoOpen] = useState(false);
  // Action Center-only — per the user (2026-07-31), this explains that
  // page's own status-card thresholds, so it doesn't make sense on the
  // record module pages or Analytics.
  const isActionCenter = useLocation().pathname === "/";

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
        // Below the preview panel's backdrop (zIndex 40, see
        // InvestigationPreviewPanel.tsx) rather than above it — the backdrop
        // should dim the whole page, header strip included, while the panel
        // is open, not just the content below it.
        zIndex: isPanelOpen ? 30 : "auto",
        // position can't be transitioned by CSS, so becoming sticky is
        // instant — this keyframe animation (plays fresh every time
        // isPanelOpen flips to true, since animation-name only (re)starts
        // when its value actually changes) slides the header down over the
        // same 250ms ease the preview panel itself opens with.
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
        {isActionCenter && (
          <div style={{ position: "relative" }}>
            <button
              type="button"
              aria-label="Investigation status thresholds"
              onClick={() => setInfoOpen((prev) => !prev)}
              style={{ background: "none", border: "none", width: 40, height: 40, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center" }}
            >
              <img src={headerIconInfo} alt="" width={20} height={20} />
            </button>

            {infoOpen && (
              <>
                <div onClick={() => setInfoOpen(false)} style={{ position: "fixed", inset: 0, zIndex: 10 }} />
                <div
                  style={{
                    position: "absolute",
                    // Anchored to the button's right edge (like the account
                    // menu panel below) so it opens leftward into the header,
                    // not rightward off the edge of a 40px-wide wrapper —
                    // that was pushing the whole page wider (per the user,
                    // 2026-07-31).
                    right: 0,
                    top: 48,
                    background: "var(--color-surface)",
                    border: "1px solid var(--color-card-border)",
                    borderRadius: "var(--radius-card)",
                    boxShadow: "0 10px 15px rgba(0,0,0,0.15)",
                    padding: 16,
                    zIndex: 20,
                  }}
                >
                  <InvestigationStatusInfo />
                </div>
              </>
            )}
          </div>
        )}

        <AppFeedbackButton />

        <button
          type="button"
          aria-label="Toggle dark mode"
          onClick={toggleTheme}
          style={{ background: "none", border: "none", width: 40, height: 40, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center" }}
        >
          <img src={headerIcon1} alt="" width={20} height={20} />
        </button>

        {/* While "view as" is active, show that investigator's name instead
            of the real signed-in user's — switches back to fullName the
            moment viewAsInvestigator is cleared (2026-08-18, per the user). */}
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
                    <option value={DEMO_VIEW_AS_INVESTIGATOR}>{DEMO_VIEW_AS_INVESTIGATOR} (most open investigations)</option>
                  </select>
                </div>

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
