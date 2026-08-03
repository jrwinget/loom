// owner-facing lifecycle controls for a case: litigation hold (a
// preservation lock), archive (a reversible status change), and purge
// (irreversible destruction). purge is gated behind a closed/archived
// status so live work can't be destroyed in a single step; while a
// hold is active both archive and purge are disabled entirely and the
// backend refuses them too.

import { useState } from 'react';
import { useUpdateCase } from '@/hooks/use-case';
import { useReleaseHold, useSetHold } from '@/hooks/use-case-hold';
import type { Case } from '@/types';
import { formatHoldDate } from './case-hold-banner';
import { CasePurgeDialog } from './case-purge-dialog';

interface CaseDangerZoneProps {
  caseData: Case;
  onPurged: () => void;
}

const HOLD_DISABLED_NOTE = 'Disabled while the case is under litigation hold.';

export function CaseDangerZone({
  caseData,
  onPurged,
}: CaseDangerZoneProps): React.ReactElement {
  const [purgeOpen, setPurgeOpen] = useState(false);
  const [holdReason, setHoldReason] = useState('');
  const [releaseReason, setReleaseReason] = useState('');
  const updateCase = useUpdateCase();
  const setHold = useSetHold(caseData.id);
  const releaseHold = useReleaseHold(caseData.id);

  const isHeld = caseData.holdActive;
  const isPurgeable =
    !isHeld && (caseData.status === 'closed' || caseData.status === 'archived');
  const isArchived = caseData.status === 'archived';

  return (
    <section className="border-destructive/40 mt-8 rounded-lg border p-4">
      <h2 className="text-destructive text-sm font-semibold">Danger zone</h2>

      <div className="mt-4 flex flex-col gap-4">
        <div className="border-border rounded-md border p-3">
          <p className="text-foreground text-sm font-medium">Litigation hold</p>
          {isHeld ? (
            <>
              <p className="text-muted-foreground mt-1 text-xs">
                Held since{' '}
                {caseData.holdSetAt ? formatHoldDate(caseData.holdSetAt) : '—'}
                {caseData.holdReason ? `: ${caseData.holdReason}` : ''}
              </p>
              <label
                htmlFor="case-hold-release-reason"
                className="text-foreground mt-3 block text-sm font-medium"
              >
                Reason for releasing the hold
              </label>
              <textarea
                id="case-hold-release-reason"
                rows={2}
                value={releaseReason}
                onChange={(e) => setReleaseReason(e.target.value)}
                disabled={releaseHold.isPending}
                className="border-input bg-background text-foreground mt-1 block w-full rounded-md border px-3 py-2 text-sm"
              />
              <div className="mt-2 flex justify-end">
                <button
                  type="button"
                  onClick={() =>
                    releaseHold.mutate(releaseReason.trim(), {
                      onSuccess: () => setReleaseReason(''),
                    })
                  }
                  disabled={
                    releaseReason.trim().length === 0 || releaseHold.isPending
                  }
                  className="border-border bg-background text-foreground hover:bg-accent rounded-md border px-4 py-2 text-sm disabled:opacity-50"
                >
                  {releaseHold.isPending ? 'Releasing…' : 'Release hold'}
                </button>
              </div>
            </>
          ) : (
            <>
              <p className="text-muted-foreground mt-1 text-xs">
                Preserve all evidence during pending or anticipated litigation.
                While held, the case and its assets cannot be destroyed.
              </p>
              <label
                htmlFor="case-hold-reason"
                className="text-foreground mt-3 block text-sm font-medium"
              >
                Reason for the hold
              </label>
              <textarea
                id="case-hold-reason"
                rows={2}
                value={holdReason}
                onChange={(e) => setHoldReason(e.target.value)}
                disabled={setHold.isPending}
                className="border-input bg-background text-foreground mt-1 block w-full rounded-md border px-3 py-2 text-sm"
              />
              <div className="mt-2 flex justify-end">
                <button
                  type="button"
                  onClick={() =>
                    setHold.mutate(holdReason.trim(), {
                      onSuccess: () => setHoldReason(''),
                    })
                  }
                  disabled={holdReason.trim().length === 0 || setHold.isPending}
                  className="border-border bg-background text-foreground hover:bg-accent rounded-md border px-4 py-2 text-sm disabled:opacity-50"
                >
                  {setHold.isPending ? 'Setting…' : 'Set hold'}
                </button>
              </div>
            </>
          )}
        </div>

        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-foreground text-sm font-medium">Archive case</p>
            <p className="text-muted-foreground text-xs">
              Move the case out of active work. It stays fully intact and can be
              reopened.
            </p>
            {isHeld && (
              <p className="text-muted-foreground mt-1 text-xs italic">
                {HOLD_DISABLED_NOTE}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={() =>
              updateCase.mutate({
                id: caseData.id,
                payload: { status: 'archived' },
              })
            }
            disabled={isArchived || isHeld || updateCase.isPending}
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
            {isHeld ? (
              <p className="text-muted-foreground mt-1 text-xs italic">
                {HOLD_DISABLED_NOTE}
              </p>
            ) : (
              !isPurgeable && (
                <p className="text-muted-foreground mt-1 text-xs italic">
                  Close or archive the case before it can be destroyed.
                </p>
              )
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
        open={purgeOpen && !isHeld}
        onClose={() => setPurgeOpen(false)}
        onPurged={onPurged}
        caseId={caseData.id}
        caseTitle={caseData.name}
        assetCount={caseData.assetCount}
      />
    </section>
  );
}
