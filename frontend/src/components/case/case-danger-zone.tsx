// owner-facing lifecycle controls for a case: archive (a reversible
// status change) and purge (irreversible destruction). purge is gated
// behind a closed/archived status so live work can't be destroyed in a
// single step; when the case is still active the control is disabled
// with an explanatory note.

import { useState } from 'react';
import { useUpdateCase } from '@/hooks/use-case';
import type { Case } from '@/types';
import { CasePurgeDialog } from './case-purge-dialog';

interface CaseDangerZoneProps {
  caseData: Case;
  onPurged: () => void;
}

export function CaseDangerZone({
  caseData,
  onPurged,
}: CaseDangerZoneProps): React.ReactElement {
  const [purgeOpen, setPurgeOpen] = useState(false);
  const updateCase = useUpdateCase();

  const isPurgeable =
    caseData.status === 'closed' || caseData.status === 'archived';
  const isArchived = caseData.status === 'archived';

  return (
    <section className="border-destructive/40 mt-8 rounded-lg border p-4">
      <h2 className="text-destructive text-sm font-semibold">Danger zone</h2>

      <div className="mt-4 flex flex-col gap-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-foreground text-sm font-medium">Archive case</p>
            <p className="text-muted-foreground text-xs">
              Move the case out of active work. It stays fully intact and can be
              reopened.
            </p>
          </div>
          <button
            type="button"
            onClick={() =>
              updateCase.mutate({
                id: caseData.id,
                payload: { status: 'archived' },
              })
            }
            disabled={isArchived || updateCase.isPending}
            className="border-border bg-background text-foreground hover:bg-accent shrink-0 rounded-md border px-4 py-2 text-sm disabled:opacity-50"
          >
            {isArchived ? 'Archived' : 'Archive'}
          </button>
        </div>

        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-foreground text-sm font-medium">Destroy case</p>
            <p className="text-muted-foreground text-xs">
              Permanently delete the case, its assets, timeline, and
              annotations. An audit tombstone is preserved.
            </p>
            {!isPurgeable && (
              <p className="text-muted-foreground mt-1 text-xs italic">
                Close or archive the case before it can be destroyed.
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={() => setPurgeOpen(true)}
            disabled={!isPurgeable}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90 shrink-0 rounded-md px-4 py-2 text-sm disabled:opacity-50"
          >
            Destroy…
          </button>
        </div>
      </div>

      <CasePurgeDialog
        open={purgeOpen}
        onClose={() => setPurgeOpen(false)}
        onPurged={onPurged}
        caseId={caseData.id}
        caseTitle={caseData.name}
        assetCount={caseData.assetCount}
      />
    </section>
  );
}
