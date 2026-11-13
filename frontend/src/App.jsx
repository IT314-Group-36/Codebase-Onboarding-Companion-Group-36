import { lazy, Suspense } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import AppLayout from './layouts/AppLayout';
import RequireAuth from './components/RequireAuth';
import LoginPage from './pages/LoginPage';
import AuthCallbackPage from './pages/AuthCallbackPage';
const DashboardPage = lazy(() => import('./pages/DashboardPage'));
const ConnectRepoPage = lazy(() => import('./pages/ConnectRepoPage'));
const RepoOverviewPage = lazy(() => import('./pages/RepoOverviewPage'));
const ExplorerPage = lazy(() => import('./pages/ExplorerPage'));
const DependencyMapPage = lazy(() => import('./pages/DependencyMapPage'));
const OnboardingPage = lazy(() => import('./pages/OnboardingPage'));
const QAPage = lazy(() => import('./pages/QAPage'));
const HistoryPage = lazy(() => import('./pages/HistoryPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));
import LoadingState from './components/LoadingState';
import NotFoundPage from './pages/NotFoundPage';

/**
 * CODEVERSE — Codebase Onboarding Companion
 * Main application router with AuthProvider and dedicated sub-view routes.
 */
export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Suspense fallback={<LoadingState message="Loading…" />}>
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
        </Suspense>
      </BrowserRouter>
    </AuthProvider>
  );
}
