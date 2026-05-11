import { useEffect, useRef } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Header } from '@/components/layout/header';
import { OfflineBanner } from '@/components/layout/offline-banner';
import { Sidebar } from '@/components/layout/sidebar';

export function Shell(): React.ReactElement {
  const mainRef = useRef<HTMLElement>(null);
  const { pathname } = useLocation();

  // move keyboard focus to the main region on every route change so
  // screen-reader and keyboard users land at the new page content
  // instead of staying on the now-stale link they clicked.
  useEffect(() => {
    mainRef.current?.focus();
  }, [pathname]);

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
          ref={mainRef}
          id="main-content"
          tabIndex={-1}
          className="flex-1 overflow-auto p-6 transition-all focus:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset"
          data-testid="main-content"
        >
          <Outlet />
        </main>
      </div>
    </div>
  );
}
