import { Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import BottomNav from './BottomNav';

export default function AppLayout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const displayName =
    user?.nom || user?.full_name || (user?.email ? user.email.split('@')[0] : 'Utilisateur');

  const handleLogout = () => { logout(); navigate('/login'); };

  return (
    <div className="flex flex-col min-h-screen" style={{ background: '#FAF8F5' }}>
      {/* Top bar */}
      <header className="flex items-center justify-between px-5 pt-5 pb-3 shrink-0">
        <div>
          <span className="text-xl font-extrabold tracking-widest text-gray-900">LOVA</span>
          <span className="text-[10px] font-semibold tracking-[0.35em] text-[#D95D39] uppercase block -mt-1">Fashion</span>
        </div>
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold text-white"
               style={{ background: 'linear-gradient(135deg, #D95D39, #B54A2E)' }}>
            {displayName.charAt(0).toUpperCase()}
          </div>
          <button
            onClick={handleLogout}
            className="text-xs text-gray-400 hover:text-gray-600 transition"
            title="Déconnexion"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75" />
            </svg>
          </button>
        </div>
      </header>

      {/* Page content */}
      <main className="flex-1 overflow-y-auto px-4 pb-24">
        <Outlet />
      </main>

      {/* Bottom navigation */}
      <BottomNav />
    </div>
  );
}
