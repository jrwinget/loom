// links the asset under review to a timeline event as evidence. the
// clip range prefills from the player's in/out marks when provided
// but stays editable so analysts can trim before linking.

import { useState } from 'react';
import { useLinkEvidence, useTimelineEvents } from '@/hooks/use-timeline';
import {
  EVIDENCE_RELATIONSHIPS,
  type EvidenceRelationship,
} from '@/types/timeline';

interface LinkToEventDialogProps {
  caseId: string;
  assetId: string;
  clipStart?: number;
  clipEnd?: number;
  onClose: () => void;
}

const inputClasses =
  'border-input bg-background text-foreground mt-1 block ' +
  'w-full rounded-md border px-3 py-1.5 text-sm';

export function LinkToEventDialog(
  props: LinkToEventDialogProps,
): React.ReactElement {
  const { caseId, assetId, clipStart, clipEnd, onClose } = props;

  const { data } = useTimelineEvents(caseId);
  const linkEvidence = useLinkEvidence();

  const events = data?.items ?? [];

  const [eventId, setEventId] = useState('');
  const [relationship, setRelationship] =
    useState<EvidenceRelationship>('supports');
  const [start, setStart] = useState(clipStart?.toString() ?? '');
  const [end, setEnd] = useState(clipEnd?.toString() ?? '');
  const [notes, setNotes] = useState('');

  const chosenEvent = eventId || events[0]?.id || '';

  const handleSubmit = (e: React.FormEvent): void => {
    e.preventDefault();
    if (!chosenEvent) return;
    linkEvidence.mutate(
      {
        caseId,
        eventId: chosenEvent,
        payload: {
          asset_id: assetId,
          relationship,
          ...(start !== '' && { clip_start: Number(start) }),
          ...(end !== '' && { clip_end: Number(end) }),
          ...(notes.trim() && { notes: notes.trim() }),
        },
      },
      { onSuccess: onClose },
    );
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="link-to-event-title"
      data-testid="link-to-event-dialog"
      className={
        'fixed inset-0 z-50 flex items-center justify-center ' +
        'bg-black/60 px-4'
      }
    >
      <form
        onSubmit={handleSubmit}
        className={
          'border-border bg-card w-full max-w-md space-y-3 ' +
          'rounded-lg border p-6'
        }
      >
        <h2
          id="link-to-event-title"
          className="text-foreground text-lg font-semibold"
        >
          Link to event
        </h2>
        <div>
          <label htmlFor="link-event" className="text-muted-foreground text-xs">
            Event
          </label>
          <select
            id="link-event"
            required
            value={chosenEvent}
            onChange={(e) => setEventId(e.target.value)}
            className={inputClasses}
          >
            {events.map((ev) => (
              <option key={ev.id} value={ev.id}>
                {ev.title}
              </option>
            ))}
          </select>
          {events.length === 0 && (
            <p className="text-muted-foreground mt-1 text-xs">
              No timeline events yet — create one on the timeline first.
            </p>
          )}
        </div>
        <div>
          <label
            htmlFor="link-relationship"
            className="text-muted-foreground text-xs"
          >
            Relationship
          </label>
          <select
            id="link-relationship"
            value={relationship}
            onChange={(e) =>
              setRelationship(e.target.value as EvidenceRelationship)
            }
            className={inputClasses}
          >
            {EVIDENCE_RELATIONSHIPS.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </select>
        </div>
        <div className="flex gap-2">
          <div className="flex-1">
            <label
              htmlFor="link-clip-start"
              className="text-muted-foreground text-xs"
            >
              Clip start (s)
            </label>
            <input
              id="link-clip-start"
              type="number"
              min={0}
              step="any"
              value={start}
              onChange={(e) => setStart(e.target.value)}
              className={inputClasses}
            />
          </div>
          <div className="flex-1">
            <label
              htmlFor="link-clip-end"
              className="text-muted-foreground text-xs"
            >
              Clip end (s)
            </label>
            <input
              id="link-clip-end"
              type="number"
              min={0}
              step="any"
              value={end}
              onChange={(e) => setEnd(e.target.value)}
              className={inputClasses}
            />
          </div>
        </div>
        <div>
          <label htmlFor="link-notes" className="text-muted-foreground text-xs">
            Notes
          </label>
          <textarea
            id="link-notes"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={2}
            className={inputClasses}
          />
        </div>
        <div className="flex justify-end gap-2 pt-2">
          <button
            type="button"
            onClick={onClose}
            className={
              'border-border rounded-md border px-3 py-1.5 ' +
              'text-muted-foreground hover:bg-accent text-sm'
            }
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={linkEvidence.isPending || !chosenEvent}
            className={
              'bg-primary rounded-md px-3 py-1.5 text-sm ' +
              'text-primary-foreground font-medium ' +
              'hover:bg-primary/90 disabled:opacity-50'
            }
          >
            {linkEvidence.isPending ? 'Linking...' : 'Link evidence'}
          </button>
        </div>
      </form>
    </div>
  );
}
