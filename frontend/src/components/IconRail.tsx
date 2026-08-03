import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import rail1 from "../assets/icons/rail-1.svg";
import rail2 from "../assets/icons/rail-2.svg";
import rail3 from "../assets/icons/rail-3.svg";
import rail4Active from "../assets/icons/rail-4-active.svg";

// Left icon rail — mirrors the Figma shell present on every screen. Figma's
// icons carry no labels or destinations, so the labels/behavior below are a
// pragmatic interpretation, not pulled from the design:
//  1. Dashboard — doubles as the expand/collapse toggle for this panel
//  2. Search — no page built yet, inert
//  3. Analytics — the reporting dashboard (rail3 node 1229:41868)
//  4. Investigations — the Action Center
const ITEMS = [
  { icon: rail1, label: "Dashboard", path: null },
  { icon: rail2, label: "Search", path: null },
  { icon: rail3, label: "Analytics", path: "/analytics" },
  { icon: rail4Active, label: "Investigations", path: "/" },
];

export function IconRail() {
  const [expanded, setExpanded] = useState(false);
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <nav
      aria-label="Primary"
      style={{
        background: "var(--color-rail-bg)",
        borderRight: "0.667px solid var(--color-card-border)",
        display: "flex",
        flexDirection: "column",
        gap: 12,
        padding: "24px 12px",
        width: expanded ? 200 : 64,
        transition: "width 150ms ease",
        flexShrink: 0,
      }}
    >
      {ITEMS.map((item, i) => {
        const isToggle = i === 0;
        const isDestination = item.path !== null;
        const isActive = item.path === "/" ? location.pathname === "/" || location.pathname.startsWith("/records") : item.path !== null && location.pathname.startsWith(item.path);
        return (
          <button
            key={item.label}
            type="button"
            onClick={() => {
              if (isToggle) setExpanded((prev) => !prev);
              else if (item.path) navigate(item.path);
            }}
            title={!expanded ? item.label : undefined}
            disabled={!isToggle && !isDestination}
            style={{
              height: 40,
              display: "flex",
              alignItems: "center",
              gap: 12,
              justifyContent: expanded ? "flex-start" : "center",
              borderRadius: "var(--radius-btn)",
              border: "none",
              padding: expanded ? "0 8px" : 0,
              background: isActive ? "var(--color-rail-active-bg)" : "transparent",
              cursor: isToggle || isDestination ? "pointer" : "default",
              opacity: !isToggle && !isDestination ? 0.6 : 1,
            }}
          >
            <img
              src={item.icon}
              alt=""
              width={24}
              height={24}
              style={{ flexShrink: 0, transform: isToggle && expanded ? "rotate(180deg)" : "none" }}
            />
            {expanded && (
              <span style={{ fontSize: "var(--font-size-base)", fontWeight: 600, color: "var(--color-text)", whiteSpace: "nowrap" }}>
                {item.label}
              </span>
            )}
          </button>
        );
      })}
    </nav>
  );
}
