import { CaseCard } from '@/components/case/case-card';
import type { Case } from '@/types';

interface CaseListProps {
  cases: Case[];
  isLoading: boolean;
}

function Skeleton(): React.ReactElement {
  return (
    <div
      data-testid="case-skeleton"
      className="animate-pulse rounded-lg border border-border bg-muted/40 p-4"
    >
      <div className="h-4 w-2/3 rounded bg-muted" />
      <div className="mt-2 h-3 w-full rounded bg-muted" />
      <div className="mt-3 h-3 w-1/3 rounded bg-muted" />
    </div>
  );
}

export function CaseList(props: CaseListProps): React.ReactElement {
  const { cases, isLoading } = props;

  if (isLoading) {
    return (
      <div
        aria-busy="true"
        aria-label="Loading cases"
        className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3"
      >
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} />
        ))}
      </div>
    );
  }

  if (cases.length === 0) {
    return (
      <div
        data-testid="empty-state"
        className="flex flex-col items-center justify-center py-16 text-center"
      >
        <p className="text-lg font-medium text-foreground">No cases yet</p>
        <p className="mt-1 text-sm text-muted-foreground">
          Create your first case to get started.
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {cases.map((c) => (
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
  );
}
