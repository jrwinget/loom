import { useCallback, useState } from 'react';
import { useIngestFromUrl } from '@/hooks/use-ingest-from-url';

type UrlStatus = 'pending' | 'submitting' | 'queued' | 'error';

interface UrlEntry {
  id: string;
  url: string;
  status: UrlStatus;
  error?: string;
}

const statusLabels: Record<UrlStatus, string> = {
  pending: 'Pending',
  submitting: 'Submitting',
  queued: 'Queued',
  error: 'Error',
};

const statusColors: Record<UrlStatus, string> = {
  pending: 'text-muted-foreground',
  submitting: 'text-blue-600 dark:text-blue-400',
  queued: 'text-green-600 dark:text-green-400',
  error: 'text-red-600 dark:text-red-400',
};

interface UrlIngestFormProps {
  caseId: string;
}

let nextId = 0;
function uid(): string {
  nextId += 1;
  return `url-${nextId}`;
}

function parseUrls(input: string): string[] {
  return input
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
}

export function UrlIngestForm(props: UrlIngestFormProps): React.ReactElement {
  const { caseId } = props;
  const [input, setInput] = useState('');
  const [entries, setEntries] = useState<UrlEntry[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const mutation = useIngestFromUrl(caseId);

  const handleSubmit = useCallback(async () => {
    const urls = parseUrls(input);
    if (urls.length === 0 || isSubmitting) return;

    const initial: UrlEntry[] = urls.map((url) => ({
      id: uid(),
      url,
      status: 'pending',
    }));
    setEntries(initial);
    setIsSubmitting(true);

    // issue one request per URL so failures report independently
    const updated: UrlEntry[] = [];
    for (const entry of initial) {
      const current: UrlEntry = {
        ...entry,
        status: 'submitting',
      };
      updated.push(current);
      setEntries([...updated, ...initial.slice(updated.length)]);

      try {
        await mutation.mutateAsync({ url: entry.url });
        current.status = 'queued';
      } catch (err) {
        current.status = 'error';
        current.error = err instanceof Error ? err.message : 'Unknown error';
      }
      setEntries([...updated, ...initial.slice(updated.length)]);
    }

    setIsSubmitting(false);
  }, [input, isSubmitting, mutation]);

  return (
    <div data-testid="url-ingest-form" className="space-y-4">
      <label
        htmlFor="url-ingest-textarea"
        className="text-sm font-medium text-foreground"
      >
        URLs (one per line)
      </label>
      <textarea
        id="url-ingest-textarea"
        data-testid="url-ingest-textarea"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        rows={5}
        className="bg-card w-full rounded-md border border-border p-2 text-sm text-foreground"
        placeholder="https://example.com/video.mp4"
        aria-label="URLs to ingest"
      />
      <button
        type="button"
        data-testid="url-ingest-submit"
        disabled={isSubmitting || input.trim().length === 0}
        onClick={() => {
          void handleSubmit();
        }}
        className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
      >
        {isSubmitting ? 'Submitting...' : 'Ingest URLs'}
      </button>

      {entries.length > 0 && (
        <div className="space-y-2" data-testid="url-ingest-status-list">
          {entries.map((e) => (
            <div
              key={e.id}
              data-testid={`url-entry-${e.id}`}
              className="bg-card flex items-center gap-3 rounded-md border border-border p-3"
            >
              <p
                className="min-w-0 flex-1 truncate text-sm text-foreground"
                data-testid="url-entry-url"
              >
                {e.url}
              </p>
              <span
                className={`text-xs font-medium ${statusColors[e.status]}`}
                data-testid="url-entry-status"
              >
                {statusLabels[e.status]}
              </span>
              {e.status === 'error' && e.error && (
                <span
                  className="text-xs text-red-600 dark:text-red-400"
                  data-testid="url-entry-error"
                >
                  {e.error}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
