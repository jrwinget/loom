import { useCallback, useState } from 'react';
import { useParams } from 'react-router-dom';
import { QueryError } from '@/components/layout/query-error';
import { ClusterReview } from '@/components/timeline/cluster-review';
import { useClusters, useProposeClusters } from '@/hooks/use-clusters';

type StatusFilter = 'all' | 'proposed' | 'accepted' | 'rejected';

export function ClustersPage(): React.ReactElement {
  const { caseId } = useParams<{ caseId: string }>();
  const safeId = caseId ?? '';

  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [windowSeconds, setWindowSeconds] = useState(60);

  const filterParam = statusFilter === 'all' ? undefined : statusFilter;

  const { data, isLoading, isError, refetch } = useClusters(
    safeId,
    filterParam,
  );
  const proposeClusters = useProposeClusters(safeId);

  const handleRunClustering = useCallback(() => {
    proposeClusters.mutate({ window_seconds: windowSeconds });
  }, [proposeClusters, windowSeconds]);

  const clusters = data?.items ?? [];

  return (
    <div className="flex flex-col gap-4 p-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-foreground">Clusters</h1>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1 text-sm text-muted-foreground">
            Window (s):
            <input
              type="number"
              min={1}
              value={windowSeconds}
              onChange={(e) => setWindowSeconds(Number(e.target.value) || 60)}
              data-testid="window-seconds-input"
              className="w-20 rounded border border-border bg-background px-2 py-1 text-sm text-foreground"
            />
          </label>
          <button
            type="button"
            data-testid="run-clustering-btn"
            onClick={handleRunClustering}
            disabled={proposeClusters.isPending}
            className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {proposeClusters.isPending ? 'Running...' : 'Run Clustering'}
          </button>
        </div>
      </div>

      {/* status filter tabs */}
      <div data-testid="cluster-filters" className="flex gap-2">
        {(['all', 'proposed', 'accepted', 'rejected'] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            data-testid={`filter-${mode}`}
            onClick={() => setStatusFilter(mode)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              statusFilter === mode
                ? 'bg-primary text-primary-foreground'
                : 'bg-muted text-muted-foreground hover:bg-accent'
            }`}
          >
            {mode.charAt(0).toUpperCase() + mode.slice(1)}
          </button>
        ))}
      </div>

      {/* error state */}
      {isError && (
        <QueryError
          message="Failed to load clusters."
          onRetry={() => void refetch()}
        />
      )}

      {/* loading state */}
      {!isError && (isLoading || proposeClusters.isPending) && (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              data-testid="cluster-skeleton"
              className="h-28 animate-pulse rounded-lg bg-muted"
            />
          ))}
        </div>
      )}

      {/* cluster review */}
      {!isError && !isLoading && !proposeClusters.isPending && (
        <ClusterReview caseId={safeId} clusters={clusters} />
      )}
    </div>
  );
}
