import { Outlet } from 'react-router-dom';
import { Header } from '@/components/layout/header';
import { OfflineBanner } from '@/components/layout/offline-banner';
import { Sidebar } from '@/components/layout/sidebar';
import { useUiStore } from '@/stores/ui-store';

export function Shell(): React.ReactElement {
  const sidebarOpen = useUiStore((s) => s.sidebarOpen);

  return (
    <div className="flex h-screen overflow-hidden">
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:fixed focus:left-2 focus:top-2 focus:z-[100] focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-sm focus:font-medium focus:text-primary-foreground"
      >
        Skip to main content
      </a>
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <OfflineBanner />
        <Header />
        <main
          id="main-content"
          tabIndex={-1}
          className={`flex-1 overflow-auto p-6 transition-all focus:outline-none ${
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
