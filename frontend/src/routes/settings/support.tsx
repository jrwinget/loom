import { useEffect, useState } from 'react';

import { getApiOrigin } from '@/lib/api-client';
import { exportDiagnostics, isTauri } from '@/lib/tauri-bridge';

// the backend version comes from the served openapi document. it
// lives at the server root, outside the /api/v1 prefix the api
// client owns, so a plain fetch is the right tool here.
function useBackendVersion(): string | null {
  const [version, setVersion] = useState<string | null>(null);

  useEffect(() => {
    const origin = getApiOrigin().replace(/\/api\/v1$/, '');
    let cancelled = false;
    fetch(`${origin}/openapi.json`)
      .then((res) => (res.ok ? res.json() : null))
      .then((doc: { info?: { version?: string } } | null) => {
        const fetched = doc?.info?.version;
        if (!cancelled && fetched) setVersion(fetched);
      })
      .catch(() => {
        // unreachable backend; the page shows "unavailable".
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return version;
}

export function SupportPage(): React.ReactElement {
  const version = useBackendVersion();
  const [exporting, setExporting] = useState(false);
  const [savedPath, setSavedPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleExport = async (): Promise<void> => {
    setExporting(true);
    setSavedPath(null);
    setError(null);
    try {
      const path = await exportDiagnostics();
      // null means the user cancelled the save dialog; keep quiet.
      if (path) setSavedPath(path);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl p-6">
      <h1 className="text-xl font-semibold text-foreground">Support</h1>
      <p className="mt-1 text-sm text-muted-foreground">
        Version details, log locations, and a one-click diagnostics export for
        support requests.
      </p>

      <section className="mt-6 rounded border border-border p-4">
        <h2 className="text-sm font-medium text-foreground">Versions</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          Loom backend: {version ?? 'unavailable'}
        </p>
      </section>

      <section className="mt-4 rounded border border-border p-4">
        <h2 className="text-sm font-medium text-foreground">Diagnostics</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          The export is a zip containing the desktop shell logs, the backend
          logs (emails and home paths are scrubbed when they are written), and a
          small version manifest. It never includes your evidence, the database,
          or stored secrets.
        </p>
        <button
          type="button"
          onClick={() => {
            void handleExport();
          }}
          disabled={exporting || !isTauri}
          className="mt-3 rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          {exporting ? 'Exporting…' : 'Export diagnostics…'}
        </button>
        {!isTauri && (
          <p className="mt-2 text-sm text-muted-foreground">
            Diagnostics export is available in the desktop app.
          </p>
        )}
        {savedPath && (
          <p role="status" className="mt-2 text-sm text-muted-foreground">
            Saved to {savedPath}
          </p>
        )}
        {error && (
          <p role="alert" className="mt-2 text-sm text-destructive">
            {error}
          </p>
        )}
      </section>

      <section className="mt-4 rounded border border-border p-4">
        <h2 className="text-sm font-medium text-foreground">Logs</h2>
        <p className="mt-2 text-sm text-muted-foreground">
          The desktop shell keeps size-capped rotating logs in your
          platform&apos;s application log folder. The backend keeps its own
          scrubbed log at{' '}
          <code className="text-xs">&lt;data dir&gt;/logs/backend.jsonl</code>.
          Both are what the diagnostics export bundles.
        </p>
      </section>
    </div>
  );
}
