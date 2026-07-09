import { useState } from 'react';
import { Link } from 'react-router-dom';
import { CaseCard } from '@/components/case/case-card';
import { CaseCreateDialog } from '@/components/case/case-create-dialog';
import { QueryError } from '@/components/layout/query-error';
import { useCaseAudit } from '@/hooks/use-audit';
import { useCases } from '@/hooks/use-case';
import { useStorageUsage } from '@/hooks/use-storage';
import { useJobStore } from '@/stores/job-store';

const RECENT_CASES = 6;

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
}

function formatWhen(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function SkeletonCards(): React.ReactElement {
  return (
    <div aria-busy="true" className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: 3 }, (_, i) => (
        <div
          key={i}
          className="h-36 animate-pulse rounded-lg border border-border bg-muted/40"
        />
      ))}
    </div>
  );
}

function ActiveJobsCard(): React.ReactElement | null {
  const jobs = useJobStore((s) => s.jobs);
  const running = jobs.filter((j) => j.status === 'running');
  if (running.length === 0) return null;

  return (
    <section
      aria-label="Active jobs"
      data-testid="dashboard-jobs"
      className="rounded-lg border border-border p-4"
    >
      <h2 className="text-sm font-semibold text-foreground">Running now</h2>
      <ul className="mt-2 space-y-1">
        {running.slice(0, 5).map((job) => (
          <li
            key={job.workflowId}
            className="truncate text-sm text-muted-foreground"
          >
            {job.label}
            {job.stage ? ` — ${job.stage}` : ''}
          </li>
        ))}
      </ul>
    </section>
  );
}

function StorageCard(): React.ReactElement | null {
  // 404-tolerant: the endpoint is lite-only and the hook does not
  // retry, so the server profile simply renders nothing
  const { data } = useStorageUsage();
  if (!data) return null;

  return (
    <section
      aria-label="Storage"
      data-testid="dashboard-storage"
      className="rounded-lg border border-border p-4"
    >
      <h2 className="text-sm font-semibold text-foreground">Storage</h2>
      <p className="mt-2 text-sm text-muted-foreground">
        {formatBytes(data.freeBytes)} free of {formatBytes(data.totalBytes)}
      </p>
      <Link
        to="/settings/storage"
        className="mt-1 inline-block text-xs text-primary hover:underline"
      >
        Manage storage
      </Link>
    </section>
  );
}

function RecentActivityCard(props: {
  caseId: string;
  caseName: string;
}): React.ReactElement | null {
  const { data } = useCaseAudit(props.caseId);
  if (!data || data.items.length === 0) return null;

  return (
    <section
      aria-label="Recent activity"
      data-testid="dashboard-activity"
      className="rounded-lg border border-border p-4"
    >
      <h2 className="text-sm font-semibold text-foreground">
        Recent activity — {props.caseName}
      </h2>
      <ul className="mt-2 space-y-1">
        {data.items.slice(0, 5).map((entry) => (
          <li key={entry.id} className="truncate text-sm text-muted-foreground">
            {entry.action.replace(/_/g, ' ')} · {formatWhen(entry.timestamp)}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function Dashboard(): React.ReactElement {
  const [createOpen, setCreateOpen] = useState(false);
  const { data: cases, isLoading, isError, refetch } = useCases();

  const recent = [...(cases ?? [])]
    .sort(
      (a, b) =>
        new Date(b.updatedAt ?? b.createdAt).getTime() -
        new Date(a.updatedAt ?? a.createdAt).getTime(),
    )
    .slice(0, RECENT_CASES);

  return (
    <div className="space-y-6" data-testid="dashboard">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-foreground">Home</h1>
        <button
          type="button"
          data-testid="dashboard-new-case"
          onClick={() => setCreateOpen(true)}
          className={
            'rounded-md bg-primary px-4 py-2 text-sm ' +
            'text-primary-foreground hover:bg-primary/90'
          }
        >
          New Case
        </button>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <ActiveJobsCard />
        <StorageCard />
        {recent[0] && (
          <RecentActivityCard caseId={recent[0].id} caseName={recent[0].name} />
        )}
      </div>

      <section aria-label="Recent cases">
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-semibold text-foreground">
            Recent cases
          </h2>
          <Link to="/cases" className="text-sm text-primary hover:underline">
            All cases
          </Link>
        </div>

        {isError && (
          <div className="mt-4">
            <QueryError
              message="Failed to load cases."
              onRetry={() => void refetch()}
            />
          </div>
        )}

        {isLoading && (
          <div className="mt-4">
            <SkeletonCards />
          </div>
        )}

        {!isLoading && !isError && recent.length === 0 && (
          <p
            className="mt-4 text-sm text-muted-foreground"
            data-testid="dashboard-empty"
          >
            No cases yet. Create your first case to get started.
          </p>
        )}

        {recent.length > 0 && (
          <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {recent.map((c) => (
              <CaseCard
                key={c.id}
                id={c.id}
                name={c.name}
                description={c.description}
                status={c.status}
                assetCount={c.assetCount}
                eventCount={c.eventCount}
                createdAt={c.createdAt}
              />
            ))}
          </div>
        )}
      </section>

      <CaseCreateDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}
