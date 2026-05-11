import { Link, useLocation, useParams } from 'react-router-dom';
import { useFirstRunStatus } from '@/hooks/use-first-run';
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

// reused by every nav <Link>; active class gives the row a
// filled background + foreground text so aria-current="page"
// is also visible to sighted users.
function navLinkClass(active: boolean): string {
  const base = 'block rounded-md px-3 py-2 text-sm';
  if (active) {
    return `${base} bg-accent font-medium text-accent-foreground`;
  }
  return `${base} text-muted-foreground hover:bg-accent hover:text-accent-foreground`;
}

interface NavLinkProps {
  to: string;
  label: string;
  collapsedGlyph: string;
  pathname: string;
  sidebarOpen: boolean;
}

function NavLink(props: NavLinkProps): React.ReactElement {
  const active = isActive(props.to, props.pathname);
  return (
    <Link
      to={props.to}
      aria-current={active ? 'page' : undefined}
      aria-label={props.sidebarOpen ? undefined : props.label}
      className={navLinkClass(active)}
    >
      {props.sidebarOpen ? props.label : props.collapsedGlyph}
    </Link>
  );
}

export function Sidebar(): React.ReactElement {
  const { caseId } = useParams<{ caseId: string }>();
  const { pathname } = useLocation();
  const sidebarOpen = useUiStore((s) => s.sidebarOpen);
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);
  // storage management only appears on desktop (lite) installs.
  const { data: firstRun } = useFirstRunStatus();
  const showStorage = firstRun?.deployment_profile === 'lite';

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
          <NavLink
            key={item.path}
            to={item.path}
            label={item.label}
            collapsedGlyph={item.label[0]}
            pathname={pathname}
            sidebarOpen={sidebarOpen}
          />
        ))}
        {caseId && (
          <NavLink
            to={`/cases/${caseId}/conflicts`}
            label="Conflicts"
            collapsedGlyph="C"
            pathname={pathname}
            sidebarOpen={sidebarOpen}
          />
        )}
        {caseId && (
          <NavLink
            to={`/cases/${caseId}/clusters`}
            label="Clusters"
            collapsedGlyph="K"
            pathname={pathname}
            sidebarOpen={sidebarOpen}
          />
        )}
        {caseId && (
          <NavLink
            to={`/cases/${caseId}/map`}
            label="Map"
            collapsedGlyph="M"
            pathname={pathname}
            sidebarOpen={sidebarOpen}
          />
        )}
        <NavLink
          to="/settings/plugins"
          label="Settings"
          collapsedGlyph="S"
          pathname={pathname}
          sidebarOpen={sidebarOpen}
        />
        {showStorage && (
          <NavLink
            to="/settings/storage"
            label="Storage"
            collapsedGlyph="D"
            pathname={pathname}
            sidebarOpen={sidebarOpen}
          />
        )}
      </nav>

      {/* collapse / expand */}
      <div className="border-t border-border p-2">
        <button
          type="button"
          onClick={toggleSidebar}
          className="w-full rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          aria-label={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
        >
          {sidebarOpen ? '←' : '→'}
        </button>
      </div>
    </aside>
  );
}
