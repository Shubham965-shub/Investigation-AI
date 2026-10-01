// Maps a route pathname to the virtual-pageview id RouteAnalytics (App.tsx) reports to PostHog.
// Pulled out of App.tsx into its own dependency-free module so it's testable without importing
// the whole app's module graph (router, posthog init, the feedback widget, etc.).
const STATIC_PAGEVIEW_IDS: Record<string, string> = {
  "/login": "login",
  "/": "action-center",
  "/analytics": "analytics",
  "/user-management": "user-management",
  "/cxo-dashboard": "cxo-dashboard",
};

export function pageIdForPath(pathname: string): string | null {
  if (STATIC_PAGEVIEW_IDS[pathname]) return STATIC_PAGEVIEW_IDS[pathname];
  const match = pathname.match(/^\/records\/[^/]+\/[^/]+\/([^/]+)(\/([^/]+))?/);
  if (!match) return null;
  const [, step, , subSegment] = match;
  if (step === "task-critique" && subSegment) return "task-critique-detail";
  return step;
}
