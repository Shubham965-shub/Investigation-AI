import posthog from "posthog-js";
import type { PostHogConfig } from "posthog-js";

const token = import.meta.env.VITE_POSTHOG_PROJECT_TOKEN as string | undefined;
const host = (import.meta.env.VITE_POSTHOG_HOST as string | undefined) ?? "https://us.i.posthog.com";

// Analytics is active only when a project token is configured — every export below becomes a no-op otherwise.
export const posthogEnabled = Boolean(token);

// Conservative capture (per the user) — this app's forms hold real pharma investigation text, so session
// replay masks all inputs/textareas and heatmaps stay off, unlike a maximal-capture default.
export function initPosthog() {
  if (!posthogEnabled) return;

  const options: Partial<PostHogConfig> = {
    api_host: host,
    person_profiles: "identified_only",
    capture_pageview: true,
    capture_pageleave: true,
    autocapture: true,
    enable_heatmaps: false,
    capture_performance: { web_vitals: true, network_timing: true },
    disable_session_recording: false,
    enable_recording_console_log: true,
    session_recording: {
      maskAllInputs: true,
      maskInputOptions: { password: true },
      collectFonts: true,
      recordCrossOriginIframes: true,
    },
  };
  // Keys not always present in the installed type defs.
  const extra = options as Record<string, unknown>;
  extra.capture_exceptions = true;
  extra.capture_dead_clicks = true;

  posthog.init(token as string, options);

  posthog.register({
    app: "investigation-ai",
    environment: import.meta.env.MODE,
    app_version: (import.meta.env.VITE_APP_VERSION as string | undefined) ?? "unknown",
  });
}

export function track(event: string, props?: Record<string, unknown>) {
  if (!posthogEnabled) return;
  posthog.capture(event, props);
}

// Fires a virtual pageview for SPA view changes (no real URL/document load).
export function capturePageview(view: string, props?: Record<string, unknown>) {
  if (!posthogEnabled) return;
  posthog.capture("$pageview", { view, ...props });
}

export { posthog };
