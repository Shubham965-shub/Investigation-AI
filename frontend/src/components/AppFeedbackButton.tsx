import { FeedbackButton } from "@strides-pharma-science-ltd/feedback-widget";
import { useAuth } from "../auth/AuthContext";
import { useTheme } from "../theme/ThemeContext";

const FEEDBACK_API_BASE_URL = import.meta.env.VITE_FEEDBACK_API_BASE_URL;

// The widget's own default button className (see its compiled bundle) is
// "fixed bottom-6 right-6 z-40 flex items-center gap-2 rounded-full
// bg-emerald-600 px-4 py-3 text-sm font-semibold text-white shadow-lg
// transition-colors hover:bg-emerald-700" — a floating pill. Per its README
// ("Restyle the default button — className... drop `fixed …` to render it
// inline where you place <FeedbackButton />"), dropping just the
// positioning classes (fixed/bottom-6/right-6/z-40) keeps its own default
// icon+label look but renders it inline in the header instead of floating.
//
// bg-emerald-600/hover:bg-emerald-700/shadow-lg are dropped entirely (not
// overridden) since they're the widget's own bundled Tailwind utilities —
// this app has no Tailwind of its own to generate a matching arbitrary-value
// class, so `app-feedback-btn` (see index.css) supplies the header-matching
// background/border/no-shadow via a plain CSS rule instead.
const HEADER_INLINE_CLASSNAME =
  "app-feedback-btn flex items-center gap-2 rounded-full px-4 py-3 text-sm font-semibold text-white transition-colors";

// The feedback service is a separate ARGUS Lighthouse app, but shares this
// backend's own JWT_SECRET (platform-wide, see backend/config/settings.py)
// — so this app's own regular session token IS a valid feedback-service
// token, no separate one to fetch. Confirmed 2026-08-03 against the
// reference platform repo (Strides-Pharma-Science-Ltd/Lab-Error-Platform).
export function AppFeedbackButton() {
  const { username } = useAuth();
  const { theme } = useTheme();

  if (!FEEDBACK_API_BASE_URL) return null;

  return (
    <FeedbackButton
      appKey="investigation-ai"
      apiBaseUrl={FEEDBACK_API_BASE_URL}
      getToken={() => localStorage.getItem("auth_token")}
      user={username ? { full_name: username } : undefined}
      theme={theme}
      className={HEADER_INLINE_CLASSNAME}
    />
  );
}