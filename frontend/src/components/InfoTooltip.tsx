import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

const GAP = 10; // distance between the icon and the tooltip box
const VIEWPORT_MARGIN = 16; // never render flush against the viewport edge

interface Placement {
  left: number;
  // Pointer/arrow position, clamped separately from `left` so it stays inside the box once the box shifts to stay on-screen.
  pointerLeft: number;
  maxHeight: number;
  // Grows away from whichever viewport edge is closer, instead of always downward off-screen.
  placement: "below" | "above";
  anchorTop: number;
  anchorBottom: number;
}

// Rendered through a portal as position: fixed (not an absolutely-positioned descendant) so it can't expand the page's scroll bounds; placement/maxHeight recompute from the icon's live position each time so a tall tooltip doesn't render past the viewport.
export function InfoTooltip({ label, width = 380, children }: { label: string; width?: number; children: ReactNode }) {
  const [hovered, setHovered] = useState(false);
  const [box, setBox] = useState<Placement | null>(null);
  const anchorRef = useRef<HTMLSpanElement | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);
  // Delayed hide so moving the cursor from icon to box (briefly over neither) doesn't prematurely close it.
  const hideTimeout = useRef<number | null>(null);

  function show() {
    if (hideTimeout.current !== null) {
      window.clearTimeout(hideTimeout.current);
      hideTimeout.current = null;
    }
    const rect = anchorRef.current?.getBoundingClientRect();
    if (rect) {
      const spaceBelow = window.innerHeight - rect.bottom - GAP - VIEWPORT_MARGIN;
      const spaceAbove = rect.top - GAP - VIEWPORT_MARGIN;
      const placement: Placement["placement"] = spaceBelow >= 200 || spaceBelow >= spaceAbove ? "below" : "above";
      // Clamp so a wide box's right edge never passes the viewport margin, same idea as the vertical clamping above.
      const maxLeft = window.innerWidth - width - VIEWPORT_MARGIN;
      const left = Math.min(rect.left, Math.max(VIEWPORT_MARGIN, maxLeft));
      const pointerLeft = Math.min(Math.max(rect.left - left, 12), width - 24);
      setBox({
        left,
        pointerLeft,
        anchorTop: rect.bottom,
        anchorBottom: rect.top,
        maxHeight: Math.max(120, placement === "below" ? spaceBelow : spaceAbove),
        placement,
      });
    }
    setHovered(true);
  }

  function scheduleHide() {
    hideTimeout.current = window.setTimeout(() => setHovered(false), 150);
  }

  // Position is only computed at show() time, so close on any page scroll rather than repositioning live; ignore scrolls that originate inside our own content div (which scrolls internally).
  useEffect(() => {
    if (!hovered) return;
    function handleScroll(e: Event) {
      if (e.target instanceof Node && contentRef.current?.contains(e.target)) return;
      setHovered(false);
    }
    window.addEventListener("scroll", handleScroll, { capture: true, passive: true });
    return () => window.removeEventListener("scroll", handleScroll, { capture: true });
  }, [hovered]);

  return (
    <span ref={anchorRef} style={{ position: "relative", display: "inline-flex", verticalAlign: "middle" }}>
      <span
        tabIndex={0}
        onMouseEnter={show}
        onMouseLeave={scheduleHide}
        onFocus={show}
        onBlur={scheduleHide}
        aria-label={label}
        style={{
          display: "inline-flex",
          alignItems: "center",
          justifyContent: "center",
          width: 18,
          height: 18,
          borderRadius: "50%",
          background: hovered ? "var(--color-primary)" : "transparent",
          border: `1.5px solid ${hovered ? "var(--color-primary)" : "var(--color-text-muted)"}`,
          color: hovered ? "#fff" : "var(--color-text-muted)",
          cursor: "help",
          flexShrink: 0,
          transition: "background 150ms ease, border-color 150ms ease, color 150ms ease",
        }}
      >
        <svg width="10" height="10" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
          <path d="M10 13.3V9.2" />
          <path d="M10 6.7h.008" />
        </svg>
      </span>

      {box &&
        createPortal(
          <div
            onMouseEnter={show}
            onMouseLeave={scheduleHide}
            style={{
              position: "fixed",
              ...(box.placement === "below" ? { top: box.anchorTop } : { bottom: window.innerHeight - box.anchorBottom }),
              left: box.left,
              zIndex: 1000,
              opacity: hovered ? 1 : 0,
              visibility: hovered ? "visible" : "hidden",
              transform: hovered ? "translateY(0)" : box.placement === "below" ? "translateY(-4px)" : "translateY(4px)",
              transition: "opacity 150ms ease, transform 150ms ease",
              pointerEvents: hovered ? "auto" : "none",
            }}
          >
            {/* Small pointer connecting the tooltip to the icon */}
            <span
              style={{
                position: "absolute",
                ...(box.placement === "below" ? { top: 3 } : { bottom: 3 }),
                left: box.pointerLeft,
                width: 10,
                height: 10,
                background: "var(--color-surface)",
                border: "1px solid var(--color-card-border)",
                ...(box.placement === "below"
                  ? { borderRight: "none", borderBottom: "none" }
                  : { borderLeft: "none", borderTop: "none" }),
                transform: "rotate(45deg)",
              }}
            />
            <div
              ref={contentRef}
              role="tooltip"
              style={{
                ...(box.placement === "below" ? { marginTop: GAP } : { marginBottom: GAP }),
                width,
                maxWidth: `calc(100vw - ${VIEWPORT_MARGIN * 2}px)`,
                maxHeight: box.maxHeight,
                overflowY: "auto",
                // Stops wheel scroll from falling through to the page once this box's own scroll is exhausted.
                overscrollBehavior: "contain",
                background: "var(--color-surface)",
                border: "1px solid var(--color-card-border)",
                borderRadius: 10,
                boxShadow: "0 12px 32px rgba(0,0,0,0.18)",
                padding: "16px 18px",
                fontSize: "var(--font-size-sm)",
                fontWeight: 400,
                color: "var(--color-text)",
                lineHeight: 1.55,
                cursor: "auto",
              }}
            >
              {children}
            </div>
          </div>,
          document.body
        )}
    </span>
  );
}