import { Outlet } from 'react-router-dom';
import { Header } from '@/components/layout/header';
import { Sidebar } from '@/components/layout/sidebar';
import { useUiStore } from '@/stores/ui-store';

export function Shell(): React.ReactElement {
  const sidebarOpen = useUiStore((s) => s.sidebarOpen);

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header />
        <main
          className={`flex-1 overflow-auto p-6 transition-all ${
            sidebarOpen ? 'ml-0' : 'ml-0'
          }`}
          data-testid="main-content"
        >
          <Outlet />
        </main>
      </div>
    </div>
  );
}
