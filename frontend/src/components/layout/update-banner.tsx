import { useState } from 'react';
import { installUpdate } from '@/lib/tauri-bridge';
import { useUpdateCheck } from '@/hooks/use-update-check';

// consent-first: the banner only ever appears after a passive check
// and nothing downloads or installs until the operator clicks. the
// install stops the sidecar cleanly first, then relaunches the app.
export function UpdateBanner(): React.ReactElement | null {
  const { update, dismiss } = useUpdateCheck();
  const [installing, setInstalling] = useState(false);
  const [error, setError] = useState('');

  if (!update) return null;

  const handleInstall = async (): Promise<void> => {
    setError('');
    setInstalling(true);
    try {
      await installUpdate();
      // on success the app relaunches; nothing to reset here
    } catch (err) {
      setError(err instanceof Error ? err.message : 'update failed');
      setInstalling(false);
    }
  };

  return (
    <div
      role="status"
      data-testid="update-banner"
      className={
        'flex items-center gap-3 border-b border-border ' +
        'bg-accent px-4 py-2 text-sm text-accent-foreground'
      }
    >
      <span className="flex-1">
        {`Loom ${update.version} is available.`}
        {error && (
          <span role="alert" className="ml-2 text-red-600 dark:text-red-400">
            {error}
          </span>
        )}
      </span>
      <button
        type="button"
        data-testid="update-install"
        onClick={handleInstall}
        disabled={installing}
        className={
          'rounded-md bg-primary px-3 py-1 text-primary-foreground ' +
          'hover:opacity-90 disabled:opacity-50'
        }
      >
        {installing ? 'Installing…' : 'Restart & update'}
      </button>
      <button
        type="button"
        data-testid="update-dismiss"
        onClick={dismiss}
        disabled={installing}
        className="text-muted-foreground hover:text-foreground"
        aria-label="Dismiss update notice"
      >
        Later
      </button>
    </div>
  );
}
