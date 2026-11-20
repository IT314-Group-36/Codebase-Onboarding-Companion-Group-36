import { useState, useEffect } from 'react';
import { Navigate } from 'react-router-dom';
import {
  Sparkles,
  AlertCircle,
  FolderTree,
  Boxes,
  CheckSquare,
  ShieldCheck,
  GitBranch,
} from 'lucide-react';
import CosmicBackground from '../components/CosmicBackground';
import Button from '../components/Button';
import GithubIcon from '../components/GithubIcon';
import { useAuth } from '../context/useAuth';
import { getAuthConfig } from '../services/api';
import './LoginPage.css';

/**
 * Page 1: Sign in with GitHub (OAuth).
 * The button sends the browser to GitHub; GitHub sends it back to /auth/callback once the
 * backend has created the session. Private repositories your account can access work after this.
 */
export default function LoginPage() {
  const { login, isAuthenticated, loading } = useAuth();
  const [githubEnabled, setGithubEnabled] = useState(null); // null = still checking
  const [redirecting, setRedirecting] = useState(false);

  useEffect(() => {
    let alive = true;
    getAuthConfig().then((config) => {
      if (alive) setGithubEnabled(Boolean(config.github_login_enabled));
    });
    return () => {
      alive = false;
    };
  }, []);

  // Already signed in: skip the login screen
  if (!loading && isAuthenticated) return <Navigate to="/dashboard" replace />;

  const handleGitHubAuth = () => {
    setRedirecting(true);
    login();
  };

  return (
    <div className="cv-login-view">
      <CosmicBackground intensity="full" />

      <div className="cv-login-container">
        {/* Left Column: welcome and three plain steps */}
        <div className="cv-login-narrative">
          <div className="cv-login-brand-header">
            <span className="cv-login-brand-name">CODEVERSE</span>
            <span className="cv-login-brand-sep">·</span>
            <span className="cv-login-brand-tagline">Understand any codebase</span>
          </div>

          <h1 className="cv-login-headline">Welcome to CODEVERSE</h1>

          <p className="cv-login-summary">
            Understand any project in minutes. Connect it from GitHub and get simple explanations,
            a picture of how it fits together, and a short plan for your first week.
          </p>

          {/* 3 Explicit Benefit Points */}
          <div className="cv-login-benefits">
            <div className="cv-login-benefit-item">
              <div className="cv-login-benefit-icon" aria-hidden="true">
                <FolderTree size={16} />
              </div>
              <div className="cv-login-benefit-text">
                <strong className="cv-login-benefit-title">1. Connect your project</strong>
                <p className="cv-login-benefit-desc">
                  Pick a project from GitHub. Nothing to download or install.
                </p>
              </div>
            </div>

            <div className="cv-login-benefit-item">
              <div className="cv-login-benefit-icon" aria-hidden="true">
                <Boxes size={16} />
              </div>
              <div className="cv-login-benefit-text">
                <strong className="cv-login-benefit-title">2. Understand it</strong>
                <p className="cv-login-benefit-desc">
                  Read any file with a plain-English explanation and see how the parts connect.
                </p>
              </div>
            </div>

            <div className="cv-login-benefit-item">
              <div className="cv-login-benefit-icon" aria-hidden="true">
                <CheckSquare size={16} />
              </div>
              <div className="cv-login-benefit-text">
                <strong className="cv-login-benefit-title">3. Ask questions</strong>
                <p className="cv-login-benefit-desc">
                  Ask in plain English and get answers that point to the exact code.
                </p>
              </div>
            </div>
          </div>

          <div className="cv-login-meta-pills">
            <span className="cv-login-meta-pill">
              <ShieldCheck size={14} /> We only read your code
            </span>
            <span className="cv-login-meta-pill">
              <GitBranch size={14} /> Sign in with your GitHub account
            </span>
          </div>
        </div>

        {/* Right Column: Premium Dark Aurora Authentication Card */}
        <div className="cv-login-panel-wrap">
          <div className="cv-auth-box">
            <div className="cv-auth-box__header">
              <div className="cv-auth-box__logo" aria-hidden="true">
                <Sparkles size={22} />
              </div>
              <h2 className="cv-auth-box__title">CODEVERSE</h2>
              <p className="cv-auth-box__tagline">Sign in to get started</p>
            </div>

            <div className="cv-auth-box__body">
              <p className="cv-auth-box__instruction">
                Sign in with your GitHub account to connect a project, including private ones you have access to.
              </p>

              {githubEnabled === false && (
                <div className="cv-auth-demo-banner" role="alert">
                  <AlertCircle size={15} className="cv-auth-demo-banner__icon" />
                  <div>
                    <strong>Sign-in is not available yet</strong>
                    <p>
                      GitHub sign-in has not been set up for this app. Please ask the person who runs it to finish the setup.
                    </p>
                  </div>
                </div>
              )}

              <div className="cv-auth-cta-stack">
                <Button
                  variant="primary"
                  size="lg"
                  loading={redirecting || loading}
                  disabled={githubEnabled === false}
                  icon={<GithubIcon size={18} />}
                  onClick={handleGitHubAuth}
                  className="cv-auth-submit-btn"
                >
                  Continue with GitHub
                </Button>
              </div>

              <p className="cv-auth-box__terms">
                We only read the projects you choose. Your GitHub sign-in is stored securely and never shown in the browser.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
