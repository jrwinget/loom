import { Link } from 'react-router-dom';
import { useUiStore } from '@/stores/ui-store';

const navItems = [
  { label: 'Dashboard', path: '/' },
  { label: 'Cases', path: '/cases' },
] as const;

export function Sidebar(): React.ReactElement {
  const sidebarOpen = useUiStore((s) => s.sidebarOpen);
  const toggleSidebar = useUiStore((s) => s.toggleSidebar);

  return (
    <aside
      data-testid="sidebar"
      className={`flex flex-col border-r border-border bg-muted/40 transition-all ${
        sidebarOpen ? 'w-60' : 'w-14'
      }`}
    >
      {/* logo / title */}
      <div className="flex h-14 items-center border-b border-border px-4">
        {sidebarOpen && (
          <span className="text-lg font-semibold text-foreground">
            Loom
          </span>
        )}
      </div>

      {/* navigation */}
      <nav className="flex-1 space-y-1 p-2">
        {navItems.map((item) => (
          <Link
            key={item.path}
            to={item.path}
            className="block rounded-md px-3 py-2 text-sm
              text-muted-foreground hover:bg-accent
              hover:text-accent-foreground"
          >
            {sidebarOpen ? item.label : item.label[0]}
          </Link>
        ))}
      </nav>

      {/* collapse / expand */}
      <div className="border-t border-border p-2">
        <button
          onClick={toggleSidebar}
          className="w-full rounded-md px-3 py-2 text-sm
            text-muted-foreground hover:bg-accent
            hover:text-accent-foreground"
          aria-label={
            sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'
          }
        >
          {sidebarOpen ? '\u2190' : '\u2192'}
        </button>
      </div>
    </aside>
  );
}
