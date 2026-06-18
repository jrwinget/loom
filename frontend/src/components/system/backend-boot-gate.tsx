import { useState } from 'react';
import { useBackendReady } from '@/hooks/use-backend-ready';
import { restartBackend } from '@/lib/tauri-bridge';

export function BackendBootGate({
  children,
}: {
  children: React.ReactNode;
}): React.ReactElement {
  const { status, error, reset } = useBackendReady();
  const [retrying, setRetrying] = useState(false);

  async function handleRetry(): Promise<void> {
    setRetrying(true);
    reset();
    try {
      await restartBackend();
    } catch {
      // restart failures surface as the next backend-error event.
    } finally {
      setRetrying(false);
    }
  }

  if (status === 'ready') {
    return <>{children}</>;
  }

  if (status === 'error') {
    return (
      <div className="flex min-h-screen items-center justify-center px-4 py-12">
        <div className="w-full max-w-lg space-y-4 rounded-lg border border-border bg-card p-8">
          <h1 className="text-xl font-semibold text-foreground">
            Loom backend did not start
          </h1>
          <p className="text-sm text-muted-foreground">
            The local backend exited before it could answer a health check. The
            captured output is below.
          </p>
          <pre
            className="max-h-64 overflow-auto rounded-md border border-border bg-muted/40 p-3 text-xs text-foreground"
            data-testid="backend-error-output"
          >
            {error ?? 'unknown error'}
          </pre>
          <button
            type="button"
            onClick={handleRetry}
            disabled={retrying}
            className="rounded-md bg-primary px-4 py-2 text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {retrying ? 'Retrying…' : 'Retry'}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-12">
      <div className="w-full max-w-md space-y-3 rounded-lg border border-border bg-card p-8 text-center">
        <h1 className="text-lg font-semibold text-foreground">
          Loom is starting…
        </h1>
        <p className="text-sm text-muted-foreground">
          Waiting for the local backend to come online.
        </p>
      </div>
    </div>
  );
}
