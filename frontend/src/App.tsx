import { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { capturePageview } from "./telemetry/posthog";
import { pageIdForPath } from "./lib/pageId";
import { AuthProvider } from "./auth/AuthContext";
import { ThemeProvider } from "./theme/ThemeContext";
import { PanelStateProvider } from "./components/PanelStateContext";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import { RootLayout } from "./components/RootLayout";
import { RecordShell } from "./components/RecordShell";
import { LoginPage } from "./pages/LoginPage";
import { ActionCenterPage } from "./pages/ActionCenterPage";
import { ProblemStatementPage } from "./pages/ProblemStatementPage";
import { EvidenceCollectionPage } from "./pages/EvidenceCollectionPage";
import { InterviewQuestionnairePage } from "./pages/InterviewQuestionnairePage";
import { RciPlanPage } from "./pages/RciPlanPage";
import { TaskCritiquePage } from "./pages/TaskCritiquePage";
import { TaskCritiqueDetailPage } from "./pages/TaskCritiqueDetailPage";
import { RcCapaCritiquePage } from "./pages/RcCapaCritiquePage";
import { RciReportPage } from "./pages/RciReportPage";
import { AnalyticsPage } from "./pages/AnalyticsPage";
import { UserManagementPage } from "./pages/UserManagementPage";
import { CxoDashboardPage } from "./pages/CxoDashboardPage";


// Fires a virtual $pageview on every SPA navigation (no real document load to hook into).
function RouteAnalytics() {
  const { pathname } = useLocation();
  useEffect(() => {
    const id = pageIdForPath(pathname);
    if (id) capturePageview(id);
  }, [pathname]);
  return null;
}

export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <AuthProvider>
          <PanelStateProvider>
          <RouteAnalytics />
          <Routes>
            <Route path="/login" element={<LoginPage />} />

            <Route
              element={
                <ProtectedRoute>
                  <RootLayout />
                </ProtectedRoute>
              }
            >
              <Route path="/" element={<ActionCenterPage />} />
              <Route path="/analytics" element={<AnalyticsPage />} />
              <Route path="/user-management" element={<UserManagementPage />} />
              <Route path="/cxo-dashboard" element={<CxoDashboardPage />} />

              <Route path="/records/:recordId" element={<Navigate to="none/problem-statement" replace />} />
              <Route path="/records/:recordId/:rciId/problem-statement" element={<RecordShell currentStep="problem-statement" />}>
                <Route index element={<ProblemStatementPage />} />
              </Route>
              <Route path="/records/:recordId/:rciId/evidence-collection" element={<RecordShell currentStep="evidence-collection" />}>
                <Route index element={<EvidenceCollectionPage />} />
              </Route>
              <Route path="/records/:recordId/:rciId/interview-questionnaire" element={<RecordShell currentStep="interview-questionnaire" />}>
                <Route index element={<InterviewQuestionnairePage />} />
              </Route>
              <Route path="/records/:recordId/:rciId/rci-plan" element={<RecordShell currentStep="rci-plan" />}>
                <Route index element={<RciPlanPage />} />
              </Route>
              <Route path="/records/:recordId/:rciId/task-critique" element={<RecordShell currentStep="task-critique" />}>
                <Route index element={<TaskCritiquePage />} />
                <Route path=":taskIndex" element={<TaskCritiqueDetailPage />} />
              </Route>
              <Route path="/records/:recordId/:rciId/rc-capa-critique" element={<RecordShell currentStep="rc-capa-critique" />}>
                <Route index element={<RcCapaCritiquePage />} />
              </Route>
              <Route path="/records/:recordId/:rciId/rci-report" element={<RecordShell currentStep="rci-report" />}>
                <Route index element={<RciReportPage />} />
              </Route>
            </Route>

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          </PanelStateProvider>
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
}
