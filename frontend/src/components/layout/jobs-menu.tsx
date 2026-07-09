import { useEffect, useRef, useState } from 'react';
import { type TrackedJob, useJobStore } from '@/stores/job-store';

const KIND_LABELS: Record<TrackedJob['kind'], string> = {
  transcription: 'Transcription',
  scene_detection: 'Scene detection',
  ocr: 'OCR',
  export: 'Export',
  url_ingest: 'URL ingest',
  ingest: 'Processing',
  bundle_import: 'Bundle import',
};

function JobProgress(props: { job: TrackedJob }): React.ReactElement {
  const { job } = props;
  const determinate =
    job.stepsTotal != null && job.stepsTotal > 0 && job.stepsDone != null;
  const pct = determinate
    ? Math.round(((job.stepsDone ?? 0) / (job.stepsTotal ?? 1)) * 100)
    : null;
  return (
    <div
      role="progressbar"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={pct ?? undefined}
      aria-label={`${job.label} progress`}
      className="bg-muted mt-1 h-1.5 w-full overflow-hidden rounded"
    >
      <div
        className={
          pct === null
            ? 'bg-primary h-full w-1/3 animate-pulse rounded'
            : 'bg-primary h-full rounded transition-all'
        }
        style={pct === null ? undefined : { width: `${pct}%` }}
      />
    </div>
  );
}

function JobRow(props: { job: TrackedJob }): React.ReactElement {
  const { job } = props;
  const dismissJob = useJobStore((s) => s.dismissJob);

  return (
    <li
      data-testid={`job-row-${job.workflowId}`}
      className="border-border border-b px-3 py-2 last:border-b-0"
    >
      <div className="flex items-center justify-between gap-2">
        <p className="text-foreground truncate text-sm">
          <span className="text-muted-foreground">
            {KIND_LABELS[job.kind]}:{' '}
          </span>
          {job.label}
        </p>
        <span
          className={
            'shrink-0 text-xs ' +
            (job.status === 'failed'
              ? 'text-destructive'
              : 'text-muted-foreground')
          }
        >
          {job.status}
        </span>
      </div>
      {job.status === 'running' && <JobProgress job={job} />}
      {job.stage && job.status === 'running' && (
        <p className="text-muted-foreground mt-1 text-xs">{job.stage}</p>
      )}
      {job.status === 'failed' && job.error && (
        <p className="text-destructive mt-1 text-xs">{job.error}</p>
      )}
      {job.status !== 'running' && (
        <div className="mt-1 flex gap-3">
          {job.status === 'failed' && job.retry && (
            <button
              type="button"
              data-testid={`job-retry-${job.workflowId}`}
              className="text-primary text-xs hover:underline"
              onClick={() => {
                dismissJob(job.workflowId);
                job.retry?.();
              }}
            >
              Retry
            </button>
          )}
          <button
            type="button"
            data-testid={`job-dismiss-${job.workflowId}`}
            className="text-muted-foreground hover:text-foreground text-xs"
            onClick={() => dismissJob(job.workflowId)}
          >
            Dismiss
          </button>
        </div>
      )}
    </li>
  );
}

// hand-rolled popup matching the header user-menu idiom; a radix
// dropdown-menu forces role="menu", which forbids progressbars inside
export function JobsMenu(): React.ReactElement {
  const jobs = useJobStore((s) => s.jobs);
  const clearFinished = useJobStore((s) => s.clearFinished);
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  const running = jobs.filter((j) => j.status === 'running').length;
  // newest first so a just-started job is visible without scrolling
  const ordered = [...jobs].sort((a, b) => b.startedAt - a.startedAt);

  useEffect(() => {
    if (!open) return;
    const handleClick = (e: MouseEvent): void => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('click', handleClick);
    return () => document.removeEventListener('click', handleClick);
  }, [open]);

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        data-testid="jobs-menu-button"
        aria-expanded={open}
        aria-label={running === 0 ? 'Jobs' : `Jobs: ${running} running`}
        className={
          'border-border relative rounded-md border px-2 py-1 ' +
          'text-muted-foreground hover:bg-accent text-xs'
        }
        onClick={() => setOpen((prev) => !prev)}
      >
        Jobs
        {running > 0 && (
          <span
            data-testid="jobs-running-badge"
            aria-hidden="true"
            className={
              'absolute -top-1.5 -right-1.5 flex h-4 min-w-4 ' +
              'bg-primary items-center justify-center rounded-full ' +
              'text-primary-foreground px-1 text-[10px] font-medium'
            }
          >
            {running}
          </span>
        )}
      </button>

      {open && (
        <div
          data-testid="jobs-menu"
          className={
            'absolute top-full right-0 z-50 mt-1 w-80 rounded-md ' +
            'border-border bg-background border shadow-lg'
          }
        >
          {ordered.length === 0 ? (
            <p className="text-muted-foreground px-3 py-4 text-sm">
              No jobs yet. Transcriptions, exports, and processing show up here.
            </p>
          ) : (
            <>
              <ul className="max-h-96 overflow-y-auto">
                {ordered.map((job) => (
                  <JobRow key={job.workflowId} job={job} />
                ))}
              </ul>
              {jobs.some((j) => j.status !== 'running') && (
                <button
                  type="button"
                  data-testid="jobs-clear-finished"
                  className={
                    'border-border w-full border-t px-3 py-2 ' +
                    'text-muted-foreground text-left text-xs ' +
                    'hover:text-foreground'
                  }
                  onClick={clearFinished}
                >
                  Clear finished
                </button>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
