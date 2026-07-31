/* eslint-disable react-refresh/only-export-components */
import { createContext, useContext, useState } from 'react';

const TOKEN_KEY = 'lova_token';

// ---------------------------------------------------------------------------
// Context
// ---------------------------------------------------------------------------
const AuthContext = createContext(null);

// ---------------------------------------------------------------------------
// Helper — safely parse stored user JSON
// ---------------------------------------------------------------------------
const getStoredUser = () => {
  try {
    const raw = localStorage.getItem('lova_user');
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
};

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------
export function AuthProvider({ children }) {
  const [user, setUser] = useState(getStoredUser);
  const [token, setToken] = useState(() => localStorage.getItem(TOKEN_KEY) || null);

  /**
   * Call this after a successful login/register API response.
   * @param {Object} userData - User object returned by the backend
   * @param {string} authToken - JWT access token
   */
  const login = (userData, authToken) => {
    localStorage.setItem(TOKEN_KEY, authToken);
    localStorage.setItem('lova_user', JSON.stringify(userData));
    setToken(authToken);
    setUser(userData);
  };

  /**
   * Clear session — removes token & user from state and localStorage.
   */
  const logout = () => {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem('lova_user');
    setToken(null);
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, token, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

// ---------------------------------------------------------------------------
// Convenience hook
// ---------------------------------------------------------------------------
export const useAuth = () => {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used inside an <AuthProvider>');
  }
  return ctx;
};

export default AuthContext;
