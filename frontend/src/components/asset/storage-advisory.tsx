import { useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useFirstRunStatus } from '@/hooks/use-first-run';
import { useStorageCheck, useStorageUsage } from '@/hooks/use-storage';

interface StorageAdvisoryProps {
  // files the user has queued but not yet uploaded. the component
  // sums their sizes and asks the backend for an advisory.
  selectedFiles: readonly File[];
}

export function StorageAdvisory(
  props: StorageAdvisoryProps,
): React.ReactElement | null {
  const { selectedFiles } = props;

  const { data: firstRun } = useFirstRunStatus();
  const isLite = firstRun?.deployment_profile === 'lite';

  const { data: usage } = useStorageUsage({ enabled: isLite });

  const check = useStorageCheck();

  const batchSize = useMemo(
    () => selectedFiles.reduce((sum, f) => sum + f.size, 0),
    [selectedFiles],
  );

  const dataDir = usage?.dataDir ?? null;
  const mutate = check.mutate;
  const reset = check.reset;

  useEffect(() => {
    if (!isLite || !dataDir || batchSize <= 0) {
      reset();
      return;
    }
    mutate({ path: dataDir, estimatedBatchSize: batchSize });
  }, [isLite, dataDir, batchSize, mutate, reset]);

  if (!isLite) return null;
  if (!check.data) return null;
  if (check.data.advisory !== 'warning') return null;

  return (
    <div
      role="alert"
      data-testid="storage-advisory"
      className="border-warning/60 bg-warning/10 mb-3 flex flex-col gap-2 rounded-md border p-3 text-sm text-foreground sm:flex-row sm:items-center sm:justify-between"
    >
      <div>
        <p className="font-medium">Low free space on data drive</p>
        {check.data.advisoryReason && (
          <p className="text-muted-foreground">{check.data.advisoryReason}</p>
        )}
      </div>
      <Link
        to="/settings/storage"
        className="shrink-0 rounded-md border border-border bg-background px-3 py-1 text-xs font-medium text-foreground hover:bg-accent"
      >
        Change storage in Settings
      </Link>
    </div>
  );
}
