import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';

export default function Navbar() {
  const auth = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    auth.logout();
    navigate('/login');
  };

  // Derive display name: prefer full_name, then username, then email prefix
  const displayName =
    auth.user?.nom ||
    auth.user?.full_name ||
    (auth.user?.email ? auth.user.email.split('@')[0] : 'User');

  return (
    <header className="flex items-center justify-between h-14 px-6 bg-white border-b border-gray-200 shrink-0">
      {/* Page title slot — children modules can customise via context if needed */}
      <div className="text-sm font-semibold text-gray-700 tracking-wide uppercase">
        LOVA FASHION
      </div>

      <div className="flex items-center gap-4">
        {/* User badge */}
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-full bg-rose-100 text-rose-600 flex items-center justify-center text-sm font-bold uppercase select-none">
            {displayName.charAt(0)}
          </div>
          <span className="text-sm font-medium text-gray-800 hidden sm:block">
            {displayName}
          </span>
        </div>

        {/* Logout */}
        <button
          type="button"
          onClick={handleLogout}
          className="text-sm px-3 py-1.5 rounded-md border border-gray-300 text-gray-600 hover:bg-gray-50 hover:border-gray-400 transition-colors"
        >
          Logout
        </button>
      </div>
    </header>
  );
}
