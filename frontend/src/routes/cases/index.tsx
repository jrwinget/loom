import { useState } from 'react';
import { CaseCreateDialog } from '@/components/case/case-create-dialog';
import { CaseList } from '@/components/case/case-list';
import { QueryError } from '@/components/layout/query-error';
import { useCases } from '@/hooks/use-case';

export function CaseListPage(): React.ReactElement {
  const { data: cases, isLoading, isError, refetch } = useCases();
  const [dialogOpen, setDialogOpen] = useState(false);

  return (
    <div className="space-y-6">
      {/* page header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">Cases</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Manage your investigation cases.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setDialogOpen(true)}
          className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          Create Case
        </button>
      </div>

      {isError && (
        <QueryError
          message="Failed to load cases."
          onRetry={() => void refetch()}
        />
      )}

      {!isError && <CaseList cases={cases ?? []} isLoading={isLoading} />}

      <CaseCreateDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </div>
  );
}
