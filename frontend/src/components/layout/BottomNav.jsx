import { NavLink } from 'react-router-dom';
import { useLanguage } from '../../context/LanguageContext';
import { NAV_ITEMS } from './Navitems';

// Mobile-only: hidden from md breakpoint up, Sidebar takes over on desktop.
export default function BottomNav() {
  const { t } = useLanguage();

  return (
    <nav
      className="md:hidden fixed bottom-0 left-0 right-0 z-50 flex items-center justify-around px-2 py-2 border-t border-gray-200"
      style={{ background: 'rgba(250,248,245,0.95)', backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' }}
      aria-label="Navigation principale"
    >
      {NAV_ITEMS.map(({ path, labelKey, icon }) => (
        <NavLink
          key={path}
          to={path}
          className="flex flex-col items-center gap-1 px-3 py-1 rounded-xl transition-all"
        >
          {({ isActive }) => (
            <>
              <span className={`transition-transform ${isActive ? 'scale-110' : 'scale-100'}`}>
                {icon(isActive)}
              </span>
              <span className={`text-[10px] font-medium tracking-tight ${isActive ? 'text-terracotta' : 'text-gray-400'}`}>
                {t(labelKey)}
              </span>
              {isActive && (
                <span className="w-1 h-1 rounded-full bg-terracotta" />
              )}
            </>
          )}
        </NavLink>
      ))}
    </nav>
  );
}