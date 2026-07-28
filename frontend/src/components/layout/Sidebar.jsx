import { NavLink } from 'react-router-dom';

const modules = [
  { number: 1, label: 'Auth & Profile',   path: '/modules/1' },
  { number: 2, label: 'Measurements',     path: '/modules/2' },
  { number: 3, label: 'Fabric Catalog',   path: '/modules/3' },
  { number: 4, label: 'Pattern Catalog',  path: '/modules/4' },
  { number: 5, label: 'Ease Margins',     path: '/modules/5' },
  { number: 6, label: 'Compatibility',    path: '/modules/6' },
  { number: 7, label: 'Final Report',     path: '/modules/7' },
];

export default function Sidebar() {
  return (
    <aside className="flex flex-col w-64 min-h-screen bg-gray-900 text-white shrink-0">
      {/* Branding */}
      <div className="flex items-center gap-2 px-6 py-5 border-b border-gray-700">
        <span className="text-rose-400 font-extrabold text-xl tracking-widest uppercase">
          LOVA
        </span>
        <span className="text-white font-light text-xl tracking-widest uppercase">
          FASHION
        </span>
      </div>

      {/* Navigation */}
      <nav className="flex flex-col gap-1 px-3 py-4 flex-1" aria-label="Module navigation">
        {modules.map(({ number, label, path }) => (
          <NavLink
            key={number}
            to={path}
            className={({ isActive }) =>
              [
                'flex items-center gap-3 px-4 py-2.5 rounded-lg text-sm font-medium transition-colors',
                isActive
                  ? 'bg-rose-500 text-white'
                  : 'text-gray-300 hover:bg-gray-700 hover:text-white',
              ].join(' ')
            }
          >
            <span className="flex items-center justify-center w-6 h-6 rounded-full bg-white/10 text-xs font-bold shrink-0">
              {number}
            </span>
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Footer */}
      <div className="px-6 py-4 border-t border-gray-700 text-xs text-gray-500">
        © {new Date().getFullYear()} LOVA FASHION
      </div>
    </aside>
  );
}
