import { Link, NavLink, Outlet, useParams } from 'react-router-dom';
import { useCase } from '@/hooks/use-case';

// every page that lives under a case shares this toolbar so the case
// workspace is reachable and self-consistent; the routes are nested
// under this layout in app.tsx.
const SECTIONS: { to: string; label: string; end?: boolean }[] = [
  { to: '.', label: 'Overview', end: true },
  { to: 'assets', label: 'Assets' },
  { to: 'timeline', label: 'Timeline' },
  { to: 'conflicts', label: 'Conflicts' },
  { to: 'clusters', label: 'Clusters' },
  { to: 'map', label: 'Map' },
  { to: 'export', label: 'Export' },
];

const statusColors: Record<string, string> = {
  active: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
  archived: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200',
  exported: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
};

function sectionClass({ isActive }: { isActive: boolean }): string {
  const base = 'px-3 py-2 text-sm';
  return isActive
    ? `${base} border-b-2 border-primary font-medium text-foreground`
    : `${base} text-muted-foreground hover:text-foreground`;
}

export function CaseLayout(): React.ReactElement {
  const { caseId } = useParams<{ caseId: string }>();
  const { data: caseData } = useCase(caseId ?? '');
  const colorClass =
    statusColors[caseData?.status ?? ''] ?? statusColors['archived'];

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <Link
          to="/cases"
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          ‹ Cases
        </Link>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold text-foreground">
            {caseData?.name ?? 'Case'}
          </h1>
          {caseData && (
            <span
              data-testid="status-badge"
              className={
                'inline-flex items-center rounded-full px-2 py-0.5 ' +
                'text-xs font-medium ' +
                colorClass
              }
            >
              {caseData.status}
            </span>
          )}
        </div>
      </div>
      <nav
        aria-label="Case sections"
        className="flex gap-1 border-b border-border"
      >
        {SECTIONS.map((s) => (
          <NavLink key={s.label} to={s.to} end={s.end} className={sectionClass}>
            {s.label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}
