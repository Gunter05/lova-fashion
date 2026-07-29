import { NavLink } from 'react-router-dom';

const NAV_ITEMS = [
  {
    path: '/modules/7',
    label: 'Inspiration',
    icon: (active) => (
      <svg className={`w-6 h-6 ${active ? 'text-terracotta' : 'text-gray-400'}`} fill={active ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 9.75L12 3l9 6.75V21a.75.75 0 01-.75.75H15.75v-4.5h-7.5v4.5H3.75A.75.75 0 013 21V9.75z" />
      </svg>
    ),
  },
  {
    path: '/modules/2',
    label: 'Mesures',
    icon: (active) => (
      <svg className={`w-6 h-6 ${active ? 'text-terracotta' : 'text-gray-400'}`} fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M6.75 7.5l3 2.25-3 2.25m4.5 0h3m-9 8.25h13.5A2.25 2.25 0 0021 18V6a2.25 2.25 0 00-2.25-2.25H5.25A2.25 2.25 0 003 6v12a2.25 2.25 0 002.25 2.25z" />
      </svg>
    ),
  },
  {
    path: '/modules/3',
    label: 'Catalogue',
    icon: (active) => (
      <svg className={`w-6 h-6 ${active ? 'text-terracotta' : 'text-gray-400'}`} fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
      </svg>
    ),
  },
  {
    path: '/modules/1',
    label: 'Mon Profil',
    icon: (active) => (
      <svg className={`w-6 h-6 ${active ? 'text-terracotta' : 'text-gray-400'}`} fill={active ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 6a3.75 3.75 0 11-7.5 0 3.75 3.75 0 017.5 0zM4.501 20.118a7.5 7.5 0 0114.998 0A17.933 17.933 0 0112 21.75c-2.676 0-5.216-.584-7.499-1.632z" />
      </svg>
    ),
  },
];

export default function BottomNav() {
  return (
    <nav
      className="fixed bottom-0 left-0 right-0 z-50 flex items-center justify-around px-2 py-2 border-t border-gray-200"
      style={{ background: 'rgba(250,248,245,0.95)', backdropFilter: 'blur(12px)', WebkitBackdropFilter: 'blur(12px)' }}
      aria-label="Navigation principale"
    >
      {NAV_ITEMS.map(({ path, label, icon }) => (
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
                {label}
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
