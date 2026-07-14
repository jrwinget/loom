import { useEffect, useState } from 'react';
import { useBackendReady } from '@/hooks/use-backend-ready';
import {
  exportDiagnostics,
  getLogPaths,
  restartBackend,
  type LogPaths,
} from '@/lib/tauri-bridge';

// a normal boot resolves in a few seconds; only a genuinely slow
// launch (cold self-extraction, av sweep) earns the elapsed timer
// and the reassurance copy.
const SLOW_BOOT_THRESHOLD_SECS = 10;

function ErrorPanel({
  error,
  retrying,
  onRetry,
}: {
  error: string;
  retrying: boolean;
  onRetry: () => void;
}): React.ReactElement {
  const [logPaths, setLogPaths] = useState<LogPaths | null>(null);
  const [exporting, setExporting] = useState(false);
  const [savedPath, setSavedPath] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getLogPaths()
      .then((paths) => {
        if (!cancelled) setLogPaths(paths);
      })
      .catch(() => {
        // no shell to ask; the panel still renders without paths.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleExport = async (): Promise<void> => {
    setExporting(true);
    setSavedPath(null);
    try {
      const path = await exportDiagnostics();
      // null means the user cancelled the save dialog; keep quiet.
      if (path) setSavedPath(path);
    } catch {
      // the zip failure itself lands in the shell log; nothing
      // actionable to render here beyond the paths already shown.
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-12">
      <div className="border-border bg-card w-full max-w-lg space-y-4 rounded-lg border p-8">
        <h1 className="text-foreground text-xl font-semibold">
          Loom backend did not start
        </h1>
        <p className="text-muted-foreground text-sm">
          The local backend exited before it could answer a health check. The
          captured output is below.
        </p>
        <pre
          className="border-border bg-muted/40 text-foreground max-h-64 overflow-auto rounded-md border p-3 text-xs"
          data-testid="backend-error-output"
        >
          {error}
        </pre>
        {logPaths && (
          <div className="text-muted-foreground space-y-1 text-xs">
            <p>Full logs live at:</p>
            {logPaths.shellLogDir && (
              <p className="font-mono">{logPaths.shellLogDir}</p>
            )}
            <p className="font-mono">{logPaths.backendLogDir}</p>
          </div>
        )}
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onRetry}
            disabled={retrying}
            className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-md px-4 py-2 disabled:opacity-50"
          >
            {retrying ? 'Retrying…' : 'Retry'}
          </button>
          <button
            type="button"
            onClick={() => {
              void handleExport();
            }}
            disabled={exporting}
            className="border-border text-foreground hover:bg-muted/40 rounded-md border px-4 py-2 disabled:opacity-50"
          >
            {exporting ? 'Exporting…' : 'Export diagnostics'}
          </button>
        </div>
        {savedPath && (
          <p className="text-muted-foreground text-xs">
            Saved to <span className="font-mono">{savedPath}</span>
          </p>
        )}
      </div>
    </div>
  );
}

export function BackendBootGate({
  children,
}: {
  children: React.ReactNode;
}): React.ReactElement {
  const { status, error, progress, reset } = useBackendReady();
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
      <ErrorPanel
        error={error ?? 'unknown error'}
        retrying={retrying}
        onRetry={() => {
          void handleRetry();
        }}
      />
    );
  }

  const slowBoot =
    progress !== undefined && progress.elapsedSecs >= SLOW_BOOT_THRESHOLD_SECS;

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-12">
      <div className="border-border bg-card w-full max-w-md space-y-3 rounded-lg border p-8 text-center">
        <h1 className="text-foreground text-lg font-semibold">
          Loom is starting…
        </h1>
        <p className="text-muted-foreground text-sm">
          Waiting for the local backend to come online.
        </p>
        {slowBoot && (
          <p className="text-muted-foreground text-sm">
            Still starting — {progress.elapsedSecs}s elapsed. First launch on
            this machine can take a few minutes.
          </p>
        )}
      </div>
    </div>
  );
}
