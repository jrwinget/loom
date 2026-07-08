import { useEffect } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useFirstRunStatus } from '@/hooks/use-first-run';

/**
 * Redirects to /first-run when the deploy has no users yet.
 *
 * The TanStack query result is cached for the session, so this
 * runs once per session — not on every navigation. /first-run
 * itself is exempt so the onboarding page can render.
 */
export function FirstRunGuard({
  children,
}: {
  children: React.ReactNode;
}): React.ReactElement {
  const navigate = useNavigate();
  const location = useLocation();
  const { data } = useFirstRunStatus();

  useEffect(() => {
    if (data?.firstRunRequired && location.pathname !== '/first-run') {
      navigate('/first-run', { replace: true });
    }
  }, [data, location.pathname, navigate]);

  return <>{children}</>;
}
