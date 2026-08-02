import { Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useFlow } from '../../context/FlowContext';
import { useLanguage } from '../../context/LanguageContext';
import BottomNav from './BottomNav';
import Sidebar from './Sidebar';
import JourneyProgress from '../common/JourneyProgress';

export default function AppLayout() {
  const { user, logout } = useAuth();
  const { resetFlow } = useFlow();
  const { locale, changeLanguage, t } = useLanguage();
  const navigate = useNavigate();

  const displayName =
    user?.nom || user?.full_name || (user?.email ? user.email.split('@')[0] : t('common.user'));

  const handleLogout = () => { resetFlow(); logout(); navigate('/login'); };

  return (
    <div className="flex min-h-screen" style={{ background: '#FAF8F5' }}>
      {/* Desktop nav — hidden on mobile (see Sidebar.jsx) */}
      <Sidebar />

      <div className="flex flex-col flex-1 min-w-0">
        {/* Top bar — branding shown here on mobile only (Sidebar already shows it on desktop) */}
        <header className="flex items-center justify-between px-5 md:px-8 pt-5 md:pt-6 pb-3 md:pb-4 shrink-0">
          <div className="md:hidden">
            <span className="text-xl font-extrabold tracking-widest text-gray-900">LOVA</span>
            <span className="text-[10px] font-semibold tracking-[0.35em] text-terracotta uppercase block -mt-1">
              Fashion
            </span>
          </div>
          <div className="hidden md:block" />

          <div className="flex items-center gap-3">
            <button
              onClick={() => changeLanguage(locale === 'en' ? 'fr' : 'en')}
              className="text-xs font-bold px-2 py-1 rounded-lg border border-gray-200 text-gray-600 hover:bg-gray-100 transition mr-1"
              title={locale === 'en' ? 'Passer en français' : 'Switch to English'}
            >
              {locale === 'en' ? 'FR' : 'EN'}
            </button>

            <div
              className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-bold text-white"
              style={{ background: 'linear-gradient(135deg, #D95D39, #B54A2E)' }}
            >
              {displayName.charAt(0).toUpperCase()}
            </div>
            <span className="hidden md:block text-sm font-medium text-gray-700">{displayName}</span>

            <button
              onClick={handleLogout}
              className="text-xs text-gray-400 hover:text-gray-600 transition"
              title={locale === 'en' ? 'Logout' : 'Déconnexion'}
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 9V5.25A2.25 2.25 0 0013.5 3h-6a2.25 2.25 0 00-2.25 2.25v13.5A2.25 2.25 0 007.5 21h6a2.25 2.25 0 002.25-2.25V15M12 9l-3 3m0 0l3 3m-3-3h12.75" />
              </svg>
            </button>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-y-auto pb-24 md:pb-8">
          <div className="px-4 md:px-8 pt-2 max-w-3xl md:max-w-5xl mx-auto w-full">
            <JourneyProgress />
          </div>
          <div className="px-4 md:px-8 pt-2 max-w-3xl md:max-w-5xl mx-auto w-full">
            <Outlet />
          </div>
        </main>

        {/* Mobile nav — hidden on desktop (see BottomNav.jsx) */}
        <BottomNav />
      </div>
    </div>
  );
}