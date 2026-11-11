import { useState, useEffect, useCallback } from 'react';
import { AuthContext } from './AuthContextBase';
import { loginWithGitHub, logout as apiLogout, getUserProfile } from '../services/api';
import { showToast } from '../utils/toast';

/**
 * Session state. The session itself lives in an HttpOnly cookie set by the backend;
 * this context only asks GET /auth/me who is signed in.
 */
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const res = await getUserProfile();
      setUser(res.user);
      return res.user;
    } catch {
      setUser(null); // not signed in (401) or backend unreachable
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  // Check the session once when the app loads
  useEffect(() => {
    let alive = true;
    getUserProfile()
      .then((res) => alive && setUser(res.user))
      .catch(() => alive && setUser(null)) // not signed in (401) or backend unreachable
      .finally(() => alive && setLoading(false));
    return () => {
      alive = false;
    };
  }, []);

  // Any API call that comes back 401 means the session is gone
  useEffect(() => {
    const onExpired = () => setUser(null);
    window.addEventListener('auth:expired', onExpired);
    return () => window.removeEventListener('auth:expired', onExpired);
  }, []);

  const login = useCallback(() => {
    loginWithGitHub(); // full-page redirect to GitHub
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } catch {
      // Clear client state even if the request failed
    }
    setUser(null);
    showToast('Signed out.', 'info');
  }, []);

  return (
    <AuthContext.Provider
      value={{ user, loading, isAuthenticated: Boolean(user), login, logout, refresh }}
    >
      {children}
    </AuthContext.Provider>
  );
}
