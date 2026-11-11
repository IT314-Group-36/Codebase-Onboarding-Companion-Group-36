import { useEffect } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { Sparkles, AlertCircle, CheckCircle2 } from 'lucide-react';
import { useAuth } from '../context/useAuth';
import CosmicBackground from '../components/CosmicBackground';
import Button from '../components/Button';
import './LoginPage.css';

/**
 * /auth/callback: GitHub sent the browser to the backend, which created the session and redirected here.
 * We only report the result: an `error` query parameter means sign-in failed; otherwise we wait for
 * GET /auth/me (done by AuthProvider) and continue to the dashboard.
 */
export default function AuthCallbackPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user, loading } = useAuth();
  const error = searchParams.get('error');
  const errorDescription = searchParams.get('error_description');

  let status = 'processing'; // 'processing' | 'success' | 'error'
  let errorMsg = '';
  if (error) {
    status = 'error';
    errorMsg = errorDescription || 'GitHub sign-in failed. Please try again.';
  } else if (!loading) {
    if (user) {
      status = 'success';
    } else {
      status = 'error';
      errorMsg = 'Sign-in did not complete. Please try again.';
    }
  }

  useEffect(() => {
    if (status !== 'success') return undefined;
    const timer = setTimeout(() => navigate('/dashboard', { replace: true }), 600);
    return () => clearTimeout(timer);
  }, [status, navigate]);

  return (
    <div className="cv-login-view">
      <CosmicBackground intensity="full" />
      <div className="cv-login-container" style={{ maxWidth: '480px', margin: '0 auto', textAlign: 'center' }}>
        <div className="cv-login-action-card" style={{ width: '100%' }}>
          <div className="cv-login-card-header" style={{ alignItems: 'center' }}>
            <div className="cv-login-badge">
              <Sparkles size={16} />
              <span>GitHub Sign-in</span>
            </div>
            <h2 className="cv-login-card-title">Signing you in</h2>
          </div>

          <div style={{ padding: '2rem 1rem', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1.25rem' }}>
            {status === 'processing' && (
              <>
                <div className="cv-login-spinner" style={{ width: 36, height: 36, borderWidth: 3 }} />
                <p style={{ color: 'var(--cv-text-secondary)', fontSize: '0.9375rem' }}>
                  Finishing sign-in with GitHub...
                </p>
              </>
            )}

            {status === 'success' && (
              <>
                <CheckCircle2 size={42} style={{ color: 'var(--cv-success)' }} />
                <div>
                  <h3 style={{ color: 'var(--cv-text-primary)', marginBottom: '0.25rem' }}>Signed in</h3>
                  <p style={{ color: 'var(--cv-text-secondary)', fontSize: '0.875rem' }}>
                    Redirecting to your dashboard...
                  </p>
                </div>
              </>
            )}

            {status === 'error' && (
              <>
                <AlertCircle size={42} style={{ color: 'var(--cv-danger)' }} />
                <div>
                  <h3 style={{ color: 'var(--cv-text-primary)', marginBottom: '0.25rem' }}>Sign-in Failed</h3>
                  <p style={{ color: 'var(--cv-text-secondary)', fontSize: '0.875rem', marginBottom: '1rem' }}>
                    {errorMsg}
                  </p>
                  <Link to="/">
                    <Button variant="primary" size="md">
                      Return to Sign In
                    </Button>
                  </Link>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
