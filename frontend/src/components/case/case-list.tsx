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
      className="border-border bg-muted/40 animate-pulse rounded-lg border p-4"
    >
      <div className="bg-muted h-4 w-2/3 rounded" />
      <div className="bg-muted mt-2 h-3 w-full rounded" />
      <div className="bg-muted mt-3 h-3 w-1/3 rounded" />
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
        <p className="text-foreground text-lg font-medium">No cases yet</p>
        <p className="text-muted-foreground mt-1 text-sm">
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
