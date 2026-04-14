import { Link, useLocation, useParams } from 'react-router-dom';
import { useUiStore } from '@/stores/ui-store';

const navItems = [
  { label: 'Dashboard', path: '/' },
  { label: 'Cases', path: '/cases' },
  { label: 'Organizations', path: '/organizations' },
] as const;

function isActive(path: string, pathname: string): boolean {
  if (path === '/') return pathname === '/';
  return pathname.startsWith(path);
}

export function Sidebar(): React.ReactElement {
  const { caseId } = useParams<{ caseId: string }>();
  const { pathname } = useLocation();
  const sidebarOpen = useUiStore((s) => s.sidebarOpen);
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);

  return (
    <aside
      data-testid="sidebar"
      aria-label="Main navigation"
      className={`flex flex-col border-r border-border bg-muted/40 transition-all ${
        sidebarOpen ? 'w-60' : 'w-14'
      }`}
    >
      {/* logo / title */}
      <div className="flex h-14 items-center border-b border-border px-4">
        {sidebarOpen && (
          <span className="text-lg font-semibold text-foreground">Loom</span>
        )}
      </div>

      {/* navigation */}
      <nav aria-label="Primary" className="flex-1 space-y-1 p-2">
        {navItems.map((item) => (
          <Link
            key={item.path}
            to={item.path}
            aria-current={isActive(item.path, pathname) ? 'page' : undefined}
            aria-label={sidebarOpen ? undefined : item.label}
            className="block rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            {sidebarOpen ? item.label : item.label[0]}
          </Link>
        ))}
        {caseId && (
          <Link
            to={`/cases/${caseId}/conflicts`}
            aria-current={
              isActive(`/cases/${caseId}/conflicts`, pathname)
                ? 'page'
                : undefined
            }
            aria-label={sidebarOpen ? undefined : 'Conflicts'}
            className="block rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            {sidebarOpen ? 'Conflicts' : 'C'}
          </Link>
        )}
        {caseId && (
          <Link
            to={`/cases/${caseId}/clusters`}
            aria-current={
              isActive(`/cases/${caseId}/clusters`, pathname)
                ? 'page'
                : undefined
            }
            aria-label={sidebarOpen ? undefined : 'Clusters'}
            className="block rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            {sidebarOpen ? 'Clusters' : 'K'}
          </Link>
        )}
        {caseId && (
          <Link
            to={`/cases/${caseId}/map`}
            aria-current={
              isActive(`/cases/${caseId}/map`, pathname) ? 'page' : undefined
            }
            aria-label={sidebarOpen ? undefined : 'Map'}
            className="block rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          >
            {sidebarOpen ? 'Map' : 'M'}
          </Link>
        )}
        {/* settings */}
        <Link
          to="/settings/plugins"
          aria-current={
            isActive('/settings/plugins', pathname) ? 'page' : undefined
          }
          aria-label={sidebarOpen ? undefined : 'Settings'}
          className="block rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
        >
          {sidebarOpen ? 'Settings' : 'S'}
        </Link>
      </nav>

      {/* collapse / expand */}
      <div className="border-t border-border p-2">
        <button
          type="button"
          onClick={toggleSidebar}
          className="w-full rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          aria-label={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
        >
          {sidebarOpen ? '\u2190' : '\u2192'}
        </button>
      </div>
    </aside>
  );
}
