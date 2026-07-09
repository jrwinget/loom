import { Link, matchPath, useLocation } from 'react-router-dom';
import { useCase } from '@/hooks/use-case';

interface Crumb {
  label: string;
  // crumbs without a path render as plain text (no landing page)
  path?: string;
}

const CASE_SECTIONS: Record<string, string> = {
  assets: 'Assets',
  timeline: 'Timeline',
  conflicts: 'Conflicts',
  clusters: 'Clusters',
  map: 'Map',
  export: 'Exports',
  review: 'Review',
};

const SETTINGS_PAGES: Record<string, string> = {
  ai: 'AI',
  plugins: 'Plugins',
  security: 'Security',
  storage: 'Storage',
  support: 'Support',
};

function buildCrumbs(pathname: string, caseName: string | undefined): Crumb[] {
  const crumbs: Crumb[] = [{ label: 'Home', path: '/' }];

  if (pathname.startsWith('/organizations')) {
    crumbs.push({ label: 'Organizations', path: '/organizations' });
    return crumbs;
  }

  if (pathname.startsWith('/cases')) {
    crumbs.push({ label: 'Cases', path: '/cases' });
    const sectionMatch = matchPath('/cases/:caseId/*', pathname);
    const caseId =
      sectionMatch?.params.caseId ??
      matchPath('/cases/:caseId', pathname)?.params.caseId;
    if (caseId) {
      // fall back to a neutral label until the case query resolves;
      // the case pages have already primed the cache in practice
      crumbs.push({ label: caseName ?? 'Case', path: `/cases/${caseId}` });
      const section = (sectionMatch?.params['*'] ?? '').split('/')[0];
      const sectionLabel = CASE_SECTIONS[section];
      if (sectionLabel) {
        crumbs.push({
          label: sectionLabel,
          path: `/cases/${caseId}/${section}`,
        });
      }
    }
    return crumbs;
  }

  const settingsMatch = matchPath('/settings/:page', pathname);
  if (settingsMatch) {
    // settings has no index route, so the group crumb is plain text
    crumbs.push({ label: 'Settings' });
    const pageLabel = SETTINGS_PAGES[settingsMatch.params.page ?? ''];
    if (pageLabel) {
      crumbs.push({ label: pageLabel, path: pathname });
    }
    return crumbs;
  }

  return crumbs;
}

export function Breadcrumbs(): React.ReactElement {
  const { pathname } = useLocation();
  const caseId =
    matchPath('/cases/:caseId/*', pathname)?.params.caseId ??
    matchPath('/cases/:caseId', pathname)?.params.caseId ??
    '';
  // disabled (and free) outside case routes; on case routes this hits
  // the cache the case layout already populated
  const { data: caseData } = useCase(caseId);

  const crumbs = buildCrumbs(pathname, caseData?.name);

  return (
    <nav aria-label="Breadcrumb">
      <ol className="flex items-center gap-1 text-sm text-muted-foreground">
        {crumbs.map((crumb, i) => {
          const isLast = i === crumbs.length - 1;
          return (
            <li key={`${crumb.label}-${i}`} className="flex items-center gap-1">
              {i > 0 && <span aria-hidden="true">/</span>}
              {isLast || !crumb.path ? (
                <span
                  aria-current={isLast ? 'page' : undefined}
                  className={isLast ? 'text-foreground' : undefined}
                >
                  {crumb.label}
                </span>
              ) : (
                <Link to={crumb.path} className="hover:text-foreground">
                  {crumb.label}
                </Link>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
