import { useState, useEffect, useCallback } from 'react';
import { AuthContext } from './AuthContextBase';
import { loginWithGitHub as apiLogin, logout as apiLogout, getUserProfile } from '../services/api';
import { showToast } from '../utils/toast';

const STORAGE_KEY_USER = 'codeverse_user';
const STORAGE_KEY_TOKEN = 'codeverse_token';

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY_USER);
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });

  const [token, setToken] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY_TOKEN) || null;
    } catch {
      return null;
    }
  });

  const [loading, setLoading] = useState(true);

  // Validate session on mount
  useEffect(() => {
    async function initSession() {
      if (token) {
        try {
          const res = await getUserProfile();
          if (res.success && res.user) {
            setUser(res.user);
          }
        } catch {
          // Token invalid or network issue; retain local cached user if present
        }
      }
      setLoading(false);
    }
    initSession();
  }, [token]);

  const login = useCallback(async (shouldFail = false) => {
    setLoading(true);
    try {
      const res = await apiLogin(shouldFail);
      if (res.success) {
        setUser(res.user);
        setToken(res.token);
        localStorage.setItem(STORAGE_KEY_USER, JSON.stringify(res.user));
        localStorage.setItem(STORAGE_KEY_TOKEN, res.token);
        showToast('Successfully signed in.', 'success');
        return { success: true };
      }
      throw new Error(res.error || 'Authentication failed');
    } catch (err) {
      showToast(err.message || 'Authentication error', 'error');
      return { success: false, error: err.message };
    } finally {
      setLoading(false);
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await apiLogout();
    } catch {
      // Continue client cleanup even if backend request fails
    }
    setUser(null);
    setToken(null);
    localStorage.removeItem(STORAGE_KEY_USER);
    localStorage.removeItem(STORAGE_KEY_TOKEN);
    showToast('Signed out of session.', 'info');
  }, []);

  const isAuthenticated = Boolean(user || token);

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        loading,
        isAuthenticated,
        login,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}
