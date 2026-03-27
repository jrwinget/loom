import { useCallback, useState } from 'react';
import { useParams } from 'react-router-dom';
import { QueryError } from '@/components/layout/query-error';
import { ConflictPanel } from '@/components/timeline/conflict-panel';
import { useCaseConflicts } from '@/hooks/use-conflicts';
import type { ConflictListItem } from '@/types/conflict';

type FilterMode = 'all' | 'unresolved' | 'resolved';

function statusBadge(resolved: boolean): React.ReactElement {
  return resolved ? (
    <span
      data-testid="status-badge-resolved"
      className="inline-flex items-center rounded-full bg-green-100 px-2 py-0.5 text-xs font-medium text-green-800 dark:bg-green-900 dark:text-green-200"
    >
      Resolved
    </span>
  ) : (
    <span
      data-testid="status-badge-unresolved"
      className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-900 dark:text-amber-200"
    >
      Unresolved
    </span>
  );
}

export function ConflictsPage(): React.ReactElement {
  const { caseId } = useParams<{ caseId: string }>();
  const safeId = caseId ?? '';

  const [filter, setFilter] = useState<FilterMode>('all');
  const [selectedItem, setSelectedItem] = useState<ConflictListItem | null>(
    null,
  );

  // map filter to resolved param
  const resolvedParam =
    filter === 'resolved' ? true : filter === 'unresolved' ? false : undefined;

  const {
    data,
    isLoading,
    isError,
    refetch,
  } = useCaseConflicts(safeId, resolvedParam);

  const handleSelectItem = useCallback((item: ConflictListItem) => {
    setSelectedItem(item);
  }, []);

  const handleClosePanel = useCallback(() => {
    setSelectedItem(null);
  }, []);

  const items = data?.items ?? [];
  const total = data?.total ?? 0;

  return (
    <div className="flex flex-col gap-4 p-6">
      {/* header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-foreground">
          Conflicts
          {!isLoading && (
            <span className="ml-2 text-lg font-normal text-muted-foreground">
              ({total})
            </span>
          )}
        </h1>
      </div>

      {/* filter toggles */}
      <div data-testid="conflict-filters" className="flex gap-2">
        {(['all', 'unresolved', 'resolved'] as const).map((mode) => (
          <button
            key={mode}
            type="button"
            data-testid={`filter-${mode}`}
            onClick={() => setFilter(mode)}
            className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors ${
              filter === mode
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
          message="Failed to load conflicts."
          onRetry={() => void refetch()}
        />
      )}

      {/* loading state */}
      {!isError && isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div
              key={i}
              data-testid="conflict-skeleton"
              className="h-20 animate-pulse rounded-lg bg-muted"
            />
          ))}
        </div>
      )}

      {/* empty state */}
      {!isError && !isLoading && items.length === 0 && (
        <div
          data-testid="conflicts-empty"
          className="flex h-48 items-center justify-center rounded-lg border border-dashed border-border"
        >
          <p className="text-sm text-muted-foreground">No conflicts found</p>
        </div>
      )}

      {/* conflict list */}
      {!isError && !isLoading && items.length > 0 && (
        <div className="space-y-2">
          {items.map((item) => (
            <button
              key={item.eventId}
              type="button"
              data-testid={`conflict-item-${item.eventId}`}
              onClick={() => handleSelectItem(item)}
              className="bg-card flex w-full items-center justify-between rounded-lg border border-border p-4 text-left transition-colors hover:bg-accent/30"
            >
              <div>
                <h3 className="text-sm font-semibold text-foreground">
                  {item.eventTitle}
                </h3>
                <p className="mt-0.5 text-xs text-muted-foreground">
                  {item.supportingCount} support
                  {item.supportingCount !== 1 ? 's' : ''},{' '}
                  {item.contradictingCount} contradict
                  {item.contradictingCount !== 1 ? 's' : ''}
                </p>
              </div>
              {statusBadge(item.isResolved)}
            </button>
          ))}
        </div>
      )}

      {/* conflict detail panel */}
      {selectedItem && (
        <ConflictPanel
          caseId={safeId}
          eventId={selectedItem.eventId}
          eventTitle={selectedItem.eventTitle}
          onClose={handleClosePanel}
        />
      )}
    </div>
  );
}
