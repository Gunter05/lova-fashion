import { NavLink } from 'react-router-dom';
import { useLanguage } from '../../context/LanguageContext';
import { NAV_ITEMS } from './Navitems';

// Desktop-only: hidden below md breakpoint, BottomNav takes over on mobile.
// Same NAV_ITEMS as BottomNav so the two never show different destinations.
export default function Sidebar() {
  const { t } = useLanguage();

  return (
    <aside
      className="hidden md:flex flex-col w-64 min-h-screen shrink-0 border-r border-gray-200"
      style={{ background: '#FAF8F5' }}
    >
      <div className="px-6 py-6 border-b border-gray-200">
        <span className="text-xl font-extrabold tracking-widest text-gray-900">LOVA</span>
        <span className="text-[10px] font-semibold tracking-[0.35em] text-terracotta uppercase block -mt-1">
          Fashion
        </span>
      </div>

      <nav className="flex flex-col gap-1 px-3 py-4 flex-1" aria-label="Navigation principale">
        {NAV_ITEMS.map(({ path, labelKey, icon }) => (
          <NavLink
            key={path}
            to={path}
            className={({ isActive }) =>
              [
                'flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium transition-colors',
                isActive ? 'bg-terracotta/10 text-terracotta' : 'text-gray-600 hover:bg-gray-100',
              ].join(' ')
            }
          >
            {({ isActive }) => (
              <>
                {icon(isActive)}
                {t(labelKey)}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="px-6 py-4 border-t border-gray-200 text-xs text-gray-400">
        © {new Date().getFullYear()} LOVA FASHION
      </div>
    </aside>
  );
}