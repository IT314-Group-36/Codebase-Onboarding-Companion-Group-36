import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../context/useAuth';
import LoadingState from './LoadingState';

/**
 * Route guard: everything nested inside needs a signed-in user.
 */
export default function RequireAuth() {
  const { isAuthenticated, loading } = useAuth();

  if (loading) return <LoadingState message="Checking your session..." fullPage />;
  if (!isAuthenticated) return <Navigate to="/" replace />;
  return <Outlet />;
}
