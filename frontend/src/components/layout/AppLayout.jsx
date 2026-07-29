import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import Navbar from './Navbar';

/**
 * AppLayout
 *
 * Shell layout for authenticated pages:
 *   ┌──────────────────────────────────────┐
 *   │ Sidebar │ Navbar (top)               │
 *   │         ├────────────────────────────│
 *   │         │ <Outlet /> (page content)  │
 *   └──────────────────────────────────────┘
 */
export default function AppLayout() {
  return (
    <div className="flex min-h-screen bg-gray-50">
      {/* Left sidebar */}
      <Sidebar />

      {/* Right column: navbar + main content */}
      <div className="flex flex-col flex-1 min-w-0">
        <Navbar />
        <main className="flex-1 overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
