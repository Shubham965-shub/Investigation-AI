import { useState } from "react";
import logo from "../assets/icons/logo.png";
import badge from "../assets/icons/badge.png";
import headerIcon1 from "../assets/icons/header-icon-1.svg";
import headerIcon2 from "../assets/icons/header-icon-2.svg";
import { useTheme } from "../theme/ThemeContext";
import { useAuth } from "../auth/AuthContext";
import { usePanelState } from "./PanelStateContext";

export function AppHeader() {
  const { theme, toggleTheme } = useTheme();
  const { username, logout } = useAuth();
  const { isPanelOpen } = usePanelState();
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
        zIndex: isPanelOpen ? 70 : "auto",
        // position can't be transitioned by CSS, so becoming sticky is
        // instant — this keyframe animation (plays fresh every time
        // isPanelOpen flips to true, since animation-name only (re)starts
        // when its value actually changes) slides the header down over the
        // same 250ms ease the preview panel itself opens with.
        animation: isPanelOpen ? "app-header-slide-down 250ms ease" : "none",
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <img src={logo} alt="Strides" style={{ height: 42 }} />
        <span style={{ fontSize: 24, color: "var(--color-primary)" }}>|</span>
        <span style={{ fontFamily: "var(--font-heading)", fontWeight: 700, fontSize: 24, color: "#fafafa" }}>
          Athena
        </span>
        <img src={badge} alt="" style={{ height: 42 }} />
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <button
          type="button"
          aria-label="Toggle dark mode"
          onClick={toggleTheme}
          style={{ background: "none", border: "none", width: 40, height: 40, borderRadius: "50%", display: "flex", alignItems: "center", justifyContent: "center" }}
        >
          <img src={headerIcon1} alt="" width={20} height={20} style={{ filter: theme === "dark" ? "invert(1)" : "none" }} />
        </button>

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
                  <p style={{ margin: 0, fontSize: 12, color: "var(--color-text-muted)" }}>Signed in as</p>
                  <p style={{ margin: 0, fontWeight: 700, color: "var(--color-text)" }}>{username}</p>
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
