import { FeedbackButton } from "@strides-pharma-science-ltd/feedback-widget";
import { useAuth } from "../auth/AuthContext";
import { useTheme } from "../theme/ThemeContext";

const FEEDBACK_API_BASE_URL = import.meta.env.VITE_FEEDBACK_API_BASE_URL;

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
    />
  );
}