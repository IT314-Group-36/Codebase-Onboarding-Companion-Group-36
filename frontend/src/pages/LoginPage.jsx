import { useState, useEffect, lazy, Suspense } from 'react';
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

const LiquidChromeOrb = lazy(() => import('../components/3d/LiquidChromeOrb'));

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
        {/* Left Column: Product Narrative, 3 Key Benefits & Dark Aurora AST Spec */}
        <div className="cv-login-narrative">
          <div className="cv-login-brand-tag">
            <span className="cv-login-brand-tag__dot" />
            <span>Developer Preview · Dark Aurora</span>
          </div>

          <div className="cv-login-brand-header">
            <span className="cv-login-brand-name">CODEVERSE</span>
            <span className="cv-login-brand-sep">·</span>
            <span className="cv-login-brand-tagline">Explore Your Codebase</span>
          </div>

          <h1 className="cv-login-headline">
            Understand unfamiliar codebases in minutes.
          </h1>

          <p className="cv-login-summary">
            CODEVERSE parses directory hierarchies, maps module dependencies, and generates
            actionable onboarding tasks so engineers become productive on unfamiliar repositories immediately.
          </p>

          {/* 3 Explicit Benefit Points */}
          <div className="cv-login-benefits">
            <div className="cv-login-benefit-item">
              <div className="cv-login-benefit-icon" aria-hidden="true">
                <FolderTree size={16} />
              </div>
              <div className="cv-login-benefit-text">
                <strong className="cv-login-benefit-title">1. Map project structure</strong>
                <p className="cv-login-benefit-desc">
                  Inspect comprehensive AST trees and nested directory hierarchies with zero local cloning.
                </p>
              </div>
            </div>

            <div className="cv-login-benefit-item">
              <div className="cv-login-benefit-icon" aria-hidden="true">
                <Boxes size={16} />
              </div>
              <div className="cv-login-benefit-text">
                <strong className="cv-login-benefit-title">2. Understand key modules</strong>
                <p className="cv-login-benefit-desc">
                  Trace caller/callee relationship flows, exported interfaces, and architectural entry points.
                </p>
              </div>
            </div>

            <div className="cv-login-benefit-item">
              <div className="cv-login-benefit-icon" aria-hidden="true">
                <CheckSquare size={16} />
              </div>
              <div className="cv-login-benefit-text">
                <strong className="cv-login-benefit-title">3. Complete onboarding tasks</strong>
                <p className="cv-login-benefit-desc">
                  Follow step-by-step onboarding quests designed to accelerate codebase familiarity.
                </p>
              </div>
            </div>
          </div>

          {/* Abstract Dark Aurora Architecture Graphic */}
          <div className="cv-chrome-graphic-card" aria-hidden="true">
            <div className="cv-chrome-graphic-card__head">
              <div className="cv-chrome-graphic-card__dots">
                <span className="cv-chrome-graphic-card__dot" />
                <span className="cv-chrome-graphic-card__dot" />
                <span className="cv-chrome-graphic-card__dot" />
              </div>
              <span className="cv-chrome-graphic-card__title">ast-relationship.spec</span>
              <span className="cv-chrome-graphic-card__badge">Live Graph</span>
            </div>

            <div className="cv-chrome-graphic-card__diagram">
              {/* 3D Liquid Chrome Orb with Dark Aurora reflections */}
              <div className="cv-chrome-graphic-card__orb-wrap">
                <Suspense fallback={<div style={{ width: 72, height: 72 }} />}>
                  <LiquidChromeOrb size={72} label="CODEVERSE AST Core" />
                </Suspense>
                <span className="cv-chrome-graphic-card__orb-label">AST Core</span>
              </div>

              {/* Connector line */}
              <div className="cv-metal-arrow">
                <span className="cv-metal-arrow__line" />
                <span className="cv-metal-arrow__label">analysis</span>
              </div>

              <div className="cv-metal-node cv-metal-node--entry">
                <code>App.jsx</code>
                <span className="cv-metal-node__type">Entrypoint</span>
              </div>
              <div className="cv-metal-arrow">
                <span className="cv-metal-arrow__line" />
                <span className="cv-metal-arrow__label">mounts</span>
              </div>
              <div className="cv-metal-node cv-metal-node--core">
                <code>useAuth.js</code>
                <span className="cv-metal-node__type">Context Hook</span>
              </div>
              <div className="cv-metal-arrow">
                <span className="cv-metal-arrow__line" />
                <span className="cv-metal-arrow__label">invokes</span>
              </div>
              <div className="cv-metal-node cv-metal-node--leaf">
                <code>api.js</code>
                <span className="cv-metal-node__type">HTTP Client</span>
              </div>
            </div>
          </div>

          <div className="cv-login-meta-pills">
            <span className="cv-login-meta-pill">
              <ShieldCheck size={14} /> Read-only AST parsing
            </span>
            <span className="cv-login-meta-pill">
              <GitBranch size={14} /> GitHub API integration
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
              <p className="cv-auth-box__tagline">Explore Your Codebase</p>
            </div>

            <div className="cv-auth-box__body">
              <p className="cv-auth-box__instruction">
                Sign in with GitHub to connect repositories, including private ones your account can access,
                and track onboarding roadmaps.
              </p>

              {githubEnabled === false && (
                <div className="cv-auth-demo-banner" role="alert">
                  <AlertCircle size={15} className="cv-auth-demo-banner__icon" />
                  <div>
                    <strong>GitHub sign-in is not set up</strong>
                    <p>
                      The server needs the GitHub OAuth settings in backend/.env. See the project README.
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
                We ask GitHub for read access to your repositories so we can clone the ones you choose.
                Your GitHub token is stored encrypted on the server and never sent to your browser.
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
