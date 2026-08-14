import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";

const GAP = 10; // distance between the icon and the tooltip box
const VIEWPORT_MARGIN = 16; // never render flush against the viewport edge

interface Placement {
  left: number;
  // Where the connecting pointer/arrow sits, relative to the box's own left
  // edge — normally right under the icon, but clamped separately from `left`
  // so it stays inside the box even once the box itself has been shifted
  // left to stay on-screen (see `left`'s clamping below).
  pointerLeft: number;
  maxHeight: number;
  // "below"/"above" position the box relative to the icon via top/bottom so
  // it grows away from whichever edge is closer, instead of always growing
  // downward off-screen when the icon is near the bottom of the viewport.
  placement: "below" | "above";
  anchorTop: number;
  anchorBottom: number;
}

// Shared icon + hover-tooltip mechanics for the small "i" info badges placed
// next to headings across the app (2026-08-13, per the user) — content is
// supplied by each specific caller (e.g. ProblemStatementGuidelines).
//
// Rendered through a portal into document.body as position: fixed (not a
// normal absolutely-positioned descendant) so it never affects the page's
// own layout/scrollable area — an absolutely-positioned child still expands
// its nearest scrolling ancestor's scroll bounds even though it doesn't
// shift sibling content, which was visibly "stretching" the page for a
// tooltip this size (2026-08-13, per the user).
//
// Placement (below vs. above the icon) and maxHeight are both computed from
// the icon's actual position each time it's shown — a tall tooltip anchored
// low on the page previously always grew downward capped only against the
// full viewport height, so it could render past the bottom of the screen
// with nothing to reveal the rest (2026-08-13, per the user: "gap
// identification gets hidden and cannot be scrolled to" — the last item in
// TaskCritiqueGuidelines's list, past that cutoff).
export function InfoTooltip({ label, width = 380, children }: { label: string; width?: number; children: ReactNode }) {
  const [hovered, setHovered] = useState(false);
  const [box, setBox] = useState<Placement | null>(null);
  const anchorRef = useRef<HTMLSpanElement | null>(null);
  const contentRef = useRef<HTMLDivElement | null>(null);
  // Hiding on a short delay (instead of immediately on mouseleave) means the
  // gap between the icon and the tooltip box below it — where the cursor is
  // briefly over neither element while moving from one to the other —
  // doesn't prematurely close it; entering either cancels the pending hide.
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
      // Anchoring flush to the icon's left edge overflows off the right side
      // of the screen for a wide box (e.g. the 880px score-breakdown table)
      // whenever the icon itself sits more than `width` px from the right
      // edge — clamp so the box's right edge never passes the viewport
      // margin, same idea as the existing above/below vertical clamping
      // (2026-08-14, per the user: "the dialog box... is extending out of
      // view"). The connecting pointer is clamped separately so it stays
      // inside the box while still pointing roughly at the icon.
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

  // The tooltip's position is only computed once, at show() time — if the
  // page scrolls for any reason while it's open (e.g. the wheel scroll
  // wasn't fully absorbed by the box's own overscroll-behavior below, or a
  // keyboard/scrollbar scroll elsewhere), it would otherwise stay frozen in
  // its old spot, detached from the icon (2026-08-13, per the user: "leaving
  // behind the original prompt"). Closing it outright on any scroll is
  // simpler and more robust than trying to keep repositioning it live.
  //
  // Scroll events bubble up to window, including the tooltip's own content
  // div scrolling internally (2026-08-13, per the user: scrolling the box
  // itself was closing it, then reopening already scrolled down) — so a
  // scroll that originated inside our own content div must be ignored here;
  // only a scroll of the page behind it should close the tooltip.
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
                // Stops a wheel scroll over this box from "falling through"
                // to the page behind it once this box's own scroll (if any)
                // is exhausted — including when it has no scrollable
                // overflow at all, i.e. content shorter than maxHeight
                // (2026-08-13, per the user).
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