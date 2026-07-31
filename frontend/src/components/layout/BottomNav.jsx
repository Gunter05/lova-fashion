import { NavLink } from 'react-router-dom';
import { useLanguage } from '../../context/LanguageContext';

const NAV_ITEMS = [
  {
    path: '/modules/2',
    labelKey: 'nav.measurements',
    icon: (active) => (
      <svg className={`w-6 h-6 ${active ? 'text-terracotta' : 'text-gray-400'}`} fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 7.5l3 2.25-3 2.25m4.5 0h3m-9 8.25h13.5A2.25 2.25 0 0021 18V6a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 6v12a2.25 2.25 0 002.25 2.25z" />
      </svg>
    ),
  },
  {
    path: '/modules/3',
    labelKey: 'nav.catalog',
    icon: (active) => (
      <svg className={`w-6 h-6 ${active ? 'text-terracotta' : 'text-gray-400'}`} fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
      </svg>
    ),
  },
  {
    path: '/modules/7',
    labelKey: 'nav.reports',
    icon: (active) => (
      <svg className={`w-6 h-6 ${active ? 'text-terracotta' : 'text-gray-400'}`} fill={active ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h3.75M9 15h3.75M9 18h3.75m3 .75H18a2.25 2.25 0 002.25-2.25V6.108c0-1.135-.845-2.098-1.976-2.192a48.424 48.424 0 00-1.123-.08m-5.801 0c-.065.21-.1.433-.1.664 0 .414.336.75.75.75h4.5a.75.75 0 00.75-.75 2.25 2.25 0 00-.1-.664m-5.8 0A2.251 2.251 0 0113.5 2.25H15c1.012 0 1.867.668 2.15 1.586m-5.8 0c-.376.023-.75.05-1.124.08C9.095 4.01 8.25 4.973 8.25 6.108V8.25m0 0H4.875c-.621 0-1.125.504-1.125 1.125v11.25c0 .621.504 1.125 1.125 1.125h9.75c.621 0 1.125-.504 1.125-1.125V9.375c0-.621-.504-1.125-1.125-1.125H8.25z" />
      </svg>
    ),
  },
  {
    path: '/modules/1',
    labelKey: 'nav.profile',
    icon: (active) => (
      <svg className={`w-6 h-6 ${active ? 'text-terracotta' : 'text-gray-400'}`} fill={active ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
      </svg>
    ),
  },
];

export default function BottomNav() {
  const { t } = useLanguage();

  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-50 flex items-center justify-around px-2 py-2 border-t border-gray-200"
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
