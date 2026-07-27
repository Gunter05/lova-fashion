import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

/**
 * ProtectedRoute
 *
 * Wraps a group of routes that require authentication.
 * - If the user has a valid token → renders the nested <Outlet />.
 * - If no token is present → redirects to /login (replaces history entry
 *   so the browser back button doesn't return to the protected page).
 */
export default function ProtectedRoute() {
  const { token } = useAuth();

  if (!token) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}
