import { FeedbackButton } from "@strides-pharma-science-ltd/feedback-widget";
import { useAuth } from "../auth/AuthContext";
import { useTheme } from "../theme/ThemeContext";

const FEEDBACK_API_BASE_URL = import.meta.env.VITE_FEEDBACK_API_BASE_URL;

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