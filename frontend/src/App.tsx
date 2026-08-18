import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
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

export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <AuthProvider>
          <PanelStateProvider>
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

              <Route path="/records/:recordId" element={<Navigate to="problem-statement" replace />} />
              <Route path="/records/:recordId/problem-statement" element={<RecordShell currentStep="problem-statement" />}>
                <Route index element={<ProblemStatementPage />} />
              </Route>
              <Route path="/records/:recordId/evidence-collection" element={<RecordShell currentStep="evidence-collection" />}>
                <Route index element={<EvidenceCollectionPage />} />
              </Route>
              <Route path="/records/:recordId/interview-questionnaire" element={<RecordShell currentStep="interview-questionnaire" />}>
                <Route index element={<InterviewQuestionnairePage />} />
              </Route>
              <Route path="/records/:recordId/rci-plan" element={<RecordShell currentStep="rci-plan" />}>
                <Route index element={<RciPlanPage />} />
              </Route>
              <Route path="/records/:recordId/task-critique" element={<RecordShell currentStep="task-critique" />}>
                <Route index element={<TaskCritiquePage />} />
                <Route path=":taskIndex" element={<TaskCritiqueDetailPage />} />
              </Route>
              <Route path="/records/:recordId/rc-capa-critique" element={<RecordShell currentStep="rc-capa-critique" />}>
                <Route index element={<RcCapaCritiquePage />} />
              </Route>
              <Route path="/records/:recordId/rci-report" element={<RecordShell currentStep="rci-report" />}>
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
