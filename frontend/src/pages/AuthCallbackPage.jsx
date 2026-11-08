import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import { Sparkles, AlertCircle, CheckCircle2 } from 'lucide-react';
import { useAuth } from '../context/useAuth';
import CosmicBackground from '../components/CosmicBackground';
import Button from '../components/Button';
import './LoginPage.css';

/**
 * Handles OAuth callback redirects: /auth/callback
 * Extracts authorization tokens or initiates simulated authentication handshakes.
 */
export default function AuthCallbackPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { login } = useAuth();
  const [status, setStatus] = useState('processing'); // 'processing' | 'success' | 'error'
  const [errorMsg, setErrorMsg] = useState('');

  useEffect(() => {
    let isMounted = true;

    async function handleAuth() {
      const error = searchParams.get('error');
      const errorDescription = searchParams.get('error_description');

      if (error) {
        if (isMounted) {
          setStatus('error');
          setErrorMsg(errorDescription || error || 'GitHub authorization failed.');
        }
        return;
      }

      // Simulate handshake or process incoming token/code
      try {
        const result = await login(false);
        if (result.success) {
          if (isMounted) {
            setStatus('success');
            setTimeout(() => {
              navigate('/dashboard', { replace: true });
            }, 800);
          }
        } else {
          if (isMounted) {
            setStatus('error');
            setErrorMsg(result.error || 'Failed to initialize session.');
          }
        }
      } catch (err) {
        if (isMounted) {
          setStatus('error');
          setErrorMsg(err.message || 'Authentication error.');
        }
      }
    }

    handleAuth();

    return () => {
      isMounted = false;
    };
  }, [login, navigate, searchParams]);

  return (
    <div className="cv-login-view">
      <CosmicBackground intensity="full" />
      <div className="cv-login-container" style={{ maxWidth: '480px', margin: '0 auto', textAlign: 'center' }}>
        <div className="cv-login-action-card" style={{ width: '100%' }}>
          <div className="cv-login-card-header" style={{ alignItems: 'center' }}>
            <div className="cv-login-badge">
              <Sparkles size={16} />
              <span>OAuth Callback</span>
            </div>
            <h2 className="cv-login-card-title">Authenticating Session</h2>
          </div>

          <div style={{ padding: '2rem 1rem', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '1.25rem' }}>
            {status === 'processing' && (
              <>
                <div className="cv-login-spinner" style={{ width: 36, height: 36, borderWidth: 3 }} />
                <p style={{ color: 'var(--cv-text-secondary)', fontSize: '0.9375rem' }}>
                  Negotiating OAuth session with GitHub provider...
                </p>
              </>
            )}

            {status === 'success' && (
              <>
                <CheckCircle2 size={42} style={{ color: 'var(--cv-success)' }} />
                <div>
                  <h3 style={{ color: 'var(--cv-text-primary)', marginBottom: '0.25rem' }}>Authentication Complete</h3>
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
