import { FeedbackButton } from "@strides-pharma-science-ltd/feedback-widget";
import { useAuth } from "../auth/AuthContext";
import { useTheme } from "../theme/ThemeContext";

const FEEDBACK_API_BASE_URL = import.meta.env.VITE_FEEDBACK_API_BASE_URL;

// Drops the widget's default fixed/bottom-6/right-6/z-40 positioning classes to render inline in the header; app-feedback-btn (index.css) supplies matching bg/border since this app has no Tailwind to override the widget's bundled utility classes.
const HEADER_INLINE_CLASSNAME =
  "app-feedback-btn flex items-center gap-2 rounded-full px-4 py-3 text-sm font-semibold text-white transition-colors";

// Feedback service shares this backend's JWT_SECRET, so the regular session token doubles as a valid feedback-service token.
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