import { useState, lazy, Suspense } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Sparkles,
  CheckCircle2,
  AlertCircle,
  FolderTree,
  Boxes,
  CheckSquare,
  ShieldCheck,
  GitBranch,
  Eye,
  EyeOff,
  Mail,
  Lock,
} from 'lucide-react';
import CosmicBackground from '../components/CosmicBackground';
import Button from '../components/Button';
import GithubIcon from '../components/GithubIcon';
import { useAuth } from '../context/useAuth';
import './LoginPage.css';

const LiquidChromeOrb = lazy(() => import('../components/3d/LiquidChromeOrb'));

/**
 * Page 1: Authentication / Login (Dark Aurora UI)
 * Premium developer onboarding landing view with:
 * - Ambient blue illumination and deep-space black surfaces.
 * - Minimalist login form with password visibility toggle.
 * - Amber primary login CTA.
 * - One-click GitHub OAuth authentication.
 */
export default function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuth();

  const [authMode, setAuthMode] = useState('github'); // 'github' | 'credentials'
  const [email, setEmail] = useState('alex.rivera@codeverse.dev');
  const [password, setPassword] = useState('••••••••••••');
  const [showPassword, setShowPassword] = useState(false);
  const [authState, setAuthState] = useState('idle'); // 'idle' | 'loading' | 'success' | 'error'
  const [errorMessage, setErrorMessage] = useState('');

  const handleGitHubAuth = async (shouldFail = false) => {
    setAuthState('loading');
    setErrorMessage('');

    try {
      const res = await login(shouldFail);
      if (res && res.success) {
        setAuthState('success');
        setTimeout(() => {
          navigate('/dashboard');
        }, 850);
      } else {
        setAuthState('error');
        setErrorMessage(res?.error || 'Authentication error. Please try again.');
      }
    } catch (err) {
      setAuthState('error');
      setErrorMessage(err.message || 'Authentication error. Please try again.');
    }
  };

  const handleCredentialsSubmit = async (e) => {
    e.preventDefault();
    if (!email.trim() || !password.trim()) {
      setAuthState('error');
      setErrorMessage('Please enter both work email and account password.');
      return;
    }

    setAuthState('loading');
    setErrorMessage('');

    try {
      const res = await login(false);
      if (res && res.success) {
        setAuthState('success');
        setTimeout(() => {
          navigate('/dashboard');
        }, 850);
      } else {
        setAuthState('error');
        setErrorMessage(res?.error || 'Invalid credentials. Please verify your email.');
      }
    } catch (err) {
      setAuthState('error');
      setErrorMessage(err.message || 'Failed to authenticate session.');
    }
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
              {authState === 'success' ? (
                <div className="cv-auth-success-state">
                  <CheckCircle2 size={38} className="cv-auth-success-icon" />
                  <h3>Session Initialized</h3>
                  <p>Welcome back, Alex Rivera. Redirecting to your dashboard...</p>
                </div>
              ) : (
                <>
                  {/* Mode Selector: Credentials Form vs GitHub One-Click */}
                  <div className="cv-auth-tabs">
                    <button
                      type="button"
                      className={`cv-auth-tab ${authMode === 'github' ? 'cv-auth-tab--active' : ''}`}
                      onClick={() => setAuthMode('github')}
                    >
                      GitHub OAuth
                    </button>
                    <button
                      type="button"
                      className={`cv-auth-tab ${authMode === 'credentials' ? 'cv-auth-tab--active' : ''}`}
                      onClick={() => setAuthMode('credentials')}
                    >
                      Developer Login
                    </button>
                  </div>

                  {authMode === 'credentials' ? (
                    <form className="cv-auth-form" onSubmit={handleCredentialsSubmit}>
                      <div className="cv-auth-field">
                        <label className="cv-auth-label" htmlFor="login-email">
                          Work Email
                        </label>
                        <div className="cv-auth-input-wrap">
                          <Mail size={15} className="cv-auth-input-icon" />
                          <input
                            id="login-email"
                            type="email"
                            className="cv-auth-input"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            placeholder="name@company.com"
                            required
                          />
                        </div>
                      </div>

                      <div className="cv-auth-field">
                        <label className="cv-auth-label" htmlFor="login-password">
                          Password
                        </label>
                        <div className="cv-auth-input-wrap">
                          <Lock size={15} className="cv-auth-input-icon" />
                          <input
                            id="login-password"
                            type={showPassword ? 'text' : 'password'}
                            className="cv-auth-input cv-auth-input--with-action"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            placeholder="Account password"
                            required
                          />
                          <button
                            type="button"
                            className="cv-auth-pwd-toggle"
                            onClick={() => setShowPassword(!showPassword)}
                            aria-label={showPassword ? 'Hide password' : 'Show password'}
                          >
                            {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                          </button>
                        </div>
                      </div>

                      {authState === 'error' && (
                        <div className="cv-auth-error-banner" role="alert">
                          <AlertCircle size={15} />
                          <span>{errorMessage}</span>
                        </div>
                      )}

                      <Button
                        type="submit"
                        variant="primary"
                        size="lg"
                        loading={authState === 'loading'}
                        className="cv-auth-submit-btn"
                      >
                        Sign In to Codeverse
                      </Button>
                    </form>
                  ) : (
                    <>
                      <p className="cv-auth-box__instruction">
                        Sign in with GitHub to connect repositories, parse AST nodes, and track onboarding roadmaps.
                      </p>

                      <div className="cv-auth-demo-banner" role="status">
                        <AlertCircle size={15} className="cv-auth-demo-banner__icon" />
                        <div>
                          <strong>Demo Environment</strong>
                          <p>GitHub OAuth is simulated until backend integration. Click below to enter.</p>
                        </div>
                      </div>

                      {authState === 'error' && (
                        <div className="cv-auth-error-banner" role="alert">
                          <AlertCircle size={15} />
                          <span>{errorMessage}</span>
                        </div>
                      )}

                      <div className="cv-auth-cta-stack">
                        <Button
                          variant="primary"
                          size="lg"
                          loading={authState === 'loading'}
                          icon={<GithubIcon size={18} />}
                          onClick={() => handleGitHubAuth(false)}
                          className="cv-auth-submit-btn"
                        >
                          Continue with GitHub
                        </Button>

                        <button
                          type="button"
                          className="cv-auth-simulate-toggle"
                          onClick={() => handleGitHubAuth(true)}
                          disabled={authState === 'loading'}
                        >
                          Simulate network error
                        </button>
                      </div>
                    </>
                  )}

                  <p className="cv-auth-box__terms">
                    By signing in, you agree to our{' '}
                    <a href="#terms" onClick={(e) => e.preventDefault()}>Terms</a> and{' '}
                    <a href="#privacy" onClick={(e) => e.preventDefault()}>Privacy Policy</a>.
                  </p>
                </>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
