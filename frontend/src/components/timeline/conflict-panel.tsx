import { useCallback, useState } from 'react';
import { useEventConflicts, useCreateResolution } from '@/hooks/use-conflicts';
import type { ConflictResolution, EvidenceDetail } from '@/types/conflict';

const resolutionTypes = [
  'Accepted Supporting',
  'Accepted Contradicting',
  'Noted',
  'Dismissed',
] as const;

interface ConflictPanelProps {
  caseId: string;
  eventId: string;
  eventTitle: string;
  onClose: () => void;
}

function EvidenceItem(props: {
  item: EvidenceDetail;
  variant: 'supporting' | 'contradicting';
}): React.ReactElement {
  const { item, variant } = props;
  const borderClass =
    variant === 'supporting' ? 'border-l-green-500' : 'border-l-amber-500';
  const label = item.originalFilename ?? item.assetId ?? 'Unknown';

  return (
    <div
      data-testid={`evidence-item-${item.id}`}
      className={`rounded border-l-4 ${borderClass} bg-muted/50 p-3`}
    >
      <p className="text-sm font-medium text-foreground">{label}</p>
      {(item.clipStart !== null || item.clipEnd !== null) && (
        <p className="mt-0.5 text-xs text-muted-foreground">
          Clip: {item.clipStart ?? 0}s
          {item.clipEnd !== null ? ` - ${item.clipEnd}s` : ''}
        </p>
      )}
      {item.notes && (
        <p className="mt-1 text-xs text-muted-foreground">{item.notes}</p>
      )}
    </div>
  );
}

function ResolutionEntry(props: {
  resolution: ConflictResolution;
}): React.ReactElement {
  const { resolution } = props;
  return (
    <div
      data-testid={`resolution-${resolution.id}`}
      className="rounded border border-border bg-muted/30 p-3"
    >
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-foreground">
          {resolution.resolutionType}
        </span>
        <span className="text-xs text-muted-foreground">
          {new Date(resolution.createdAt).toLocaleDateString()}
        </span>
      </div>
      {resolution.notes && (
        <p className="mt-1 text-xs text-muted-foreground">{resolution.notes}</p>
      )}
    </div>
  );
}

export function ConflictPanel(props: ConflictPanelProps): React.ReactElement {
  const { caseId, eventId, eventTitle, onClose } = props;

  const { data, isLoading } = useEventConflicts(caseId, eventId);
  const createResolution = useCreateResolution(caseId, eventId);

  const [resolutionType, setResolutionType] = useState<string>(
    resolutionTypes[0],
  );
  const [notes, setNotes] = useState('');

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      createResolution.mutate(
        { resolutionType, notes: notes || undefined },
        {
          onSuccess: () => {
            setNotes('');
          },
        },
      );
    },
    [createResolution, resolutionType, notes],
  );

  if (isLoading) {
    return (
      <div
        data-testid="conflict-panel"
        className="fixed inset-y-0 right-0 z-40 flex w-full max-w-lg flex-col border-l border-border bg-background p-6 shadow-lg"
      >
        <div className="flex animate-pulse flex-col gap-4">
          <div className="h-6 w-2/3 rounded bg-muted" />
          <div className="h-4 w-1/2 rounded bg-muted" />
          <div className="h-32 rounded bg-muted" />
        </div>
      </div>
    );
  }

  const supporting = data?.supporting ?? [];
  const contradicting = data?.contradicting ?? [];
  const resolutions = data?.resolutions ?? [];

  return (
    <>
      {/* backdrop */}
      <button
        type="button"
        className="fixed inset-0 z-30 bg-black/30"
        onClick={onClose}
        aria-label="Close conflict panel"
      />

      <div
        data-testid="conflict-panel"
        className="fixed inset-y-0 right-0 z-40 flex w-full max-w-lg flex-col overflow-y-auto border-l border-border bg-background p-6 shadow-lg"
      >
        {/* header */}
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold text-foreground">
              {eventTitle}
            </h2>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Conflict Detail
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-muted-foreground hover:text-foreground"
            aria-label="Close"
          >
            &#10005;
          </button>
        </div>

        {/* supporting evidence */}
        <section className="mt-6">
          <h3 className="text-sm font-semibold text-green-600">
            Supporting Evidence ({supporting.length})
          </h3>
          <div className="mt-2 space-y-2">
            {supporting.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No supporting evidence
              </p>
            ) : (
              supporting.map((item) => (
                <EvidenceItem key={item.id} item={item} variant="supporting" />
              ))
            )}
          </div>
        </section>

        {/* contradicting evidence */}
        <section className="mt-6">
          <h3 className="text-sm font-semibold text-amber-600">
            Contradicting Evidence ({contradicting.length})
          </h3>
          <div className="mt-2 space-y-2">
            {contradicting.length === 0 ? (
              <p className="text-xs text-muted-foreground">
                No contradicting evidence
              </p>
            ) : (
              contradicting.map((item) => (
                <EvidenceItem
                  key={item.id}
                  item={item}
                  variant="contradicting"
                />
              ))
            )}
          </div>
        </section>

        {/* resolution form */}
        <section className="mt-6">
          <h3 className="text-sm font-semibold text-foreground">
            Add Resolution
          </h3>
          <form
            data-testid="resolution-form"
            onSubmit={handleSubmit}
            className="mt-2 space-y-3"
          >
            <select
              data-testid="resolution-type-select"
              value={resolutionType}
              onChange={(e) => setResolutionType(e.target.value)}
              className="w-full rounded border border-border bg-background px-3 py-2 text-sm text-foreground"
            >
              {resolutionTypes.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <textarea
              data-testid="resolution-notes"
              placeholder="Notes (optional)"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              className="w-full rounded border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground"
            />
            <button
              type="submit"
              disabled={createResolution.isPending}
              className="rounded bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {createResolution.isPending
                ? 'Submitting...'
                : 'Submit Resolution'}
            </button>
          </form>
        </section>

        {/* existing resolutions */}
        {resolutions.length > 0 && (
          <section className="mt-6">
            <h3 className="text-sm font-semibold text-foreground">
              Resolutions ({resolutions.length})
            </h3>
            <div className="mt-2 space-y-2">
              {resolutions.map((r) => (
                <ResolutionEntry key={r.id} resolution={r} />
              ))}
            </div>
          </section>
        )}
      </div>
    </>
  );
}
