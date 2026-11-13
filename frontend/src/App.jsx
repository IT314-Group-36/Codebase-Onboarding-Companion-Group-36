import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import AppLayout from './layouts/AppLayout';
import RequireAuth from './components/RequireAuth';
import LoginPage from './pages/LoginPage';
import AuthCallbackPage from './pages/AuthCallbackPage';
import DashboardPage from './pages/DashboardPage';
import ConnectRepoPage from './pages/ConnectRepoPage';
import RepoOverviewPage from './pages/RepoOverviewPage';
import ExplorerPage from './pages/ExplorerPage';
import DependencyMapPage from './pages/DependencyMapPage';
import OnboardingPage from './pages/OnboardingPage';
import QAPage from './pages/QAPage';
import HistoryPage from './pages/HistoryPage';
import SettingsPage from './pages/SettingsPage';
import NotFoundPage from './pages/NotFoundPage';

/**
 * CODEVERSE — Codebase Onboarding Companion
 * Main application router with AuthProvider and dedicated sub-view routes.
 */
export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          {/* Public / auth */}
          <Route path="/" element={<LoginPage />} />
          <Route path="/auth/callback" element={<AuthCallbackPage />} />

          {/* Authenticated shell: redirects to the login page when not signed in */}
          <Route element={<RequireAuth />}>
            <Route element={<AppLayout />}>
              <Route path="/dashboard" element={<DashboardPage />} />
              <Route path="/connect" element={<ConnectRepoPage />} />
              <Route path="/repository/:repoId" element={<RepoOverviewPage />} />
              <Route path="/explorer/:repoId" element={<ExplorerPage />} />
              <Route path="/dependencies/:repoId" element={<DependencyMapPage />} />
              <Route path="/onboarding/:repoId" element={<OnboardingPage />} />
              <Route path="/qa/:repoId" element={<QAPage />} />
              <Route path="/history/:repoId" element={<HistoryPage />} />
              <Route path="/settings" element={<SettingsPage />} />
              <Route path="*" element={<NotFoundPage />} />
            </Route>
          </Route>
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  );
}
