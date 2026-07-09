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
          <h1 className="text-foreground text-2xl font-semibold">Cases</h1>
          <p className="text-muted-foreground mt-1 text-sm">
            Manage your investigation cases.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setDialogOpen(true)}
          className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-md px-4 py-2 text-sm font-medium"
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
