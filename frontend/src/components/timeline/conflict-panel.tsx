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
      <p className="text-foreground text-sm font-medium">{label}</p>
      {(item.clipStart !== null || item.clipEnd !== null) && (
        <p className="text-muted-foreground mt-0.5 text-xs">
          Clip: {item.clipStart ?? 0}s
          {item.clipEnd !== null ? ` - ${item.clipEnd}s` : ''}
        </p>
      )}
      {item.notes && (
        <p className="text-muted-foreground mt-1 text-xs">{item.notes}</p>
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
      className="border-border bg-muted/30 rounded border p-3"
    >
      <div className="flex items-center justify-between">
        <span className="text-foreground text-sm font-medium">
          {resolution.resolutionType}
        </span>
        <span className="text-muted-foreground text-xs">
          {new Date(resolution.createdAt).toLocaleDateString()}
        </span>
      </div>
      {resolution.notes && (
        <p className="text-muted-foreground mt-1 text-xs">{resolution.notes}</p>
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
        className="border-border bg-background fixed inset-y-0 right-0 z-40 flex w-full max-w-lg flex-col border-l p-6 shadow-lg"
      >
        <div className="flex animate-pulse flex-col gap-4">
          <div className="bg-muted h-6 w-2/3 rounded" />
          <div className="bg-muted h-4 w-1/2 rounded" />
          <div className="bg-muted h-32 rounded" />
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
        role="dialog"
        aria-modal="true"
        aria-labelledby="conflict-panel-title"
        data-testid="conflict-panel"
        className="border-border bg-background fixed inset-y-0 right-0 z-40 flex w-full max-w-lg flex-col overflow-y-auto border-l p-6 shadow-lg"
      >
        {/* header */}
        <div className="flex items-start justify-between">
          <div>
            <h2
              id="conflict-panel-title"
              className="text-foreground text-lg font-semibold"
            >
              {eventTitle}
            </h2>
            <p className="text-muted-foreground mt-0.5 text-sm">
              Conflict Detail
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground rounded p-1"
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
              <p className="text-muted-foreground text-xs">
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
              <p className="text-muted-foreground text-xs">
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
          <h3 className="text-foreground text-sm font-semibold">
            Add Resolution
          </h3>
          <form
            data-testid="resolution-form"
            onSubmit={handleSubmit}
            className="mt-2 space-y-3"
          >
            <select
              data-testid="resolution-type-select"
              aria-label="Resolution type"
              value={resolutionType}
              onChange={(e) => setResolutionType(e.target.value)}
              className="border-border bg-background text-foreground w-full rounded border px-3 py-2 text-sm"
            >
              {resolutionTypes.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </select>
            <textarea
              data-testid="resolution-notes"
              aria-label="Resolution notes"
              placeholder="Notes (optional)"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              className="border-border bg-background text-foreground placeholder:text-muted-foreground w-full rounded border px-3 py-2 text-sm"
            />
            <button
              type="submit"
              disabled={createResolution.isPending}
              className="bg-primary text-primary-foreground hover:bg-primary/90 rounded px-4 py-2 text-sm font-medium disabled:opacity-50"
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
            <h3 className="text-foreground text-sm font-semibold">
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
