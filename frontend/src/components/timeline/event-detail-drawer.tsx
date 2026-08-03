// slide-over detail panel for a timeline event. view mode mirrors the
// original inline drawer; edit mode patches the event; the evidence
// section is where "every claim traces back to source material"
// becomes actionable: list, unlink, and add evidence links.

import { useState } from 'react';
import { useAssets } from '@/hooks/use-assets';
import {
  useLinkEvidence,
  useUnlinkEvidence,
  useUpdateEvent,
} from '@/hooks/use-timeline';
import {
  EVENT_STATUSES,
  EVIDENCE_RELATIONSHIPS,
  type EventStatus,
  type EvidenceRelationship,
  type TimelineEventDetail,
} from '@/types/timeline';

interface EventDetailDrawerProps {
  caseId: string;
  event: TimelineEventDetail;
  onClose: () => void;
}

const relationshipColors: Record<EvidenceRelationship, string> = {
  supports:
    'bg-green-100 text-green-800 dark:bg-green-900 ' + 'dark:text-green-200',
  contradicts: 'bg-red-100 text-red-800 dark:bg-red-900 ' + 'dark:text-red-200',
  context: 'bg-gray-100 text-gray-800 dark:bg-gray-900 ' + 'dark:text-gray-200',
};

const inputClasses =
  'border-border mt-1 w-full rounded-md border ' +
  'bg-background text-foreground px-3 py-1.5 text-sm';

// datetime-local inputs carry minute precision in local time
function isoToLocalInput(iso: string | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n: number): string => String(n).padStart(2, '0');
  return (
    `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}` +
    `T${pad(d.getHours())}:${pad(d.getMinutes())}`
  );
}

export function EventDetailDrawer(
  props: EventDetailDrawerProps,
): React.ReactElement {
  const { caseId, event, onClose } = props;
  const [editing, setEditing] = useState(false);
  const [addingEvidence, setAddingEvidence] = useState(false);

  const { data: assets } = useAssets(caseId);
  const unlinkEvidence = useUnlinkEvidence();

  const assetNames = new Map(
    (assets ?? []).map((a) => [a.id, a.originalFilename]),
  );

  return (
    <>
      <button
        type="button"
        className="fixed inset-0 z-30 bg-black/30"
        onClick={onClose}
        aria-label="Close panel"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="event-detail-title"
        data-testid="event-detail-panel"
        className={
          'fixed inset-y-0 right-0 z-40 flex w-full ' +
          'max-w-md flex-col overflow-y-auto border-l ' +
          'border-border bg-background p-6 shadow-lg'
        }
      >
        <h2
          id="event-detail-title"
          className="text-foreground text-lg font-semibold"
        >
          {event.title}
        </h2>

        {editing ? (
          <EventEditForm
            caseId={caseId}
            event={event}
            onDone={() => setEditing(false)}
          />
        ) : (
          <>
            {event.description && (
              <p className="text-muted-foreground mt-2 text-sm">
                {event.description}
              </p>
            )}
            <div className={'text-muted-foreground mt-4 space-y-2 text-sm'}>
              <p>
                Status: <span className="font-medium">{event.status}</span>
              </p>
              <p>
                Precision:{' '}
                <span className="font-medium">{event.timePrecision}</span>
              </p>
              <p>
                Evidence:{' '}
                <span className="font-medium">
                  {event.evidenceCount} link
                  {event.evidenceCount !== 1 ? 's' : ''}
                </span>
              </p>
              {event.hasContradictions && (
                <p className="font-medium text-amber-600">
                  Has contradicting evidence
                </p>
              )}
            </div>
            <button
              type="button"
              data-testid="edit-event-btn"
              onClick={() => setEditing(true)}
              className={
                'border-border mt-4 w-fit rounded-md border px-3 ' +
                'text-muted-foreground hover:bg-accent py-1.5 text-sm'
              }
            >
              Edit
            </button>
          </>
        )}

        <section aria-label="Evidence" className="mt-6">
          <h3 className="text-foreground text-sm font-semibold">Evidence</h3>
          {event.evidence.length === 0 && (
            <p className="text-muted-foreground mt-2 text-sm">
              No evidence linked yet.
            </p>
          )}
          <ul className="mt-2 space-y-2">
            {event.evidence.map((link) => (
              <li
                key={link.id}
                data-testid={`evidence-link-${link.id}`}
                className={
                  'border-border flex items-start justify-between ' +
                  'gap-2 rounded-md border p-2 text-sm'
                }
              >
                <div className="min-w-0">
                  <span
                    data-testid="relationship-badge"
                    className={
                      'inline-flex items-center rounded-full px-2 ' +
                      'py-0.5 text-xs font-medium ' +
                      (relationshipColors[
                        link.relationship as EvidenceRelationship
                      ] ?? relationshipColors.context)
                    }
                  >
                    {link.relationship}
                  </span>
                  <p className="text-foreground mt-1 truncate">
                    {link.assetId
                      ? (assetNames.get(link.assetId) ?? 'Asset')
                      : 'Linked source'}
                  </p>
                  {link.clipStart !== null && (
                    <p className="text-muted-foreground text-xs">
                      Clip: {link.clipStart}s
                      {link.clipEnd !== null ? ` – ${link.clipEnd}s` : ''}
                    </p>
                  )}
                  {link.notes && (
                    <p className="text-muted-foreground text-xs">
                      {link.notes}
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  data-testid={`unlink-btn-${link.id}`}
                  onClick={() =>
                    unlinkEvidence.mutate({
                      caseId,
                      eventId: event.id,
                      linkId: link.id,
                    })
                  }
                  disabled={unlinkEvidence.isPending}
                  className={
                    'text-muted-foreground hover:text-destructive ' +
                    'shrink-0 text-xs underline disabled:opacity-50'
                  }
                >
                  Unlink
                </button>
              </li>
            ))}
          </ul>

          {addingEvidence ? (
            <AddEvidenceForm
              caseId={caseId}
              eventId={event.id}
              assets={assets ?? []}
              onDone={() => setAddingEvidence(false)}
            />
          ) : (
            <button
              type="button"
              data-testid="add-evidence-btn"
              onClick={() => setAddingEvidence(true)}
              className={
                'bg-primary text-primary-foreground mt-3 rounded-md ' +
                'hover:bg-primary/90 px-3 py-1.5 text-sm font-medium'
              }
            >
              Add evidence
            </button>
          )}
        </section>
      </div>
    </>
  );
}

interface EventEditFormProps {
  caseId: string;
  event: TimelineEventDetail;
  onDone: () => void;
}

function EventEditForm(props: EventEditFormProps): React.ReactElement {
  const { caseId, event, onDone } = props;
  const updateEvent = useUpdateEvent();

  const [title, setTitle] = useState(event.title);
  const [description, setDescription] = useState(event.description ?? '');
  const [start, setStart] = useState(isoToLocalInput(event.eventTimeStart));
  const [end, setEnd] = useState(isoToLocalInput(event.eventTimeEnd));
  const [precision, setPrecision] = useState(event.timePrecision);
  const [status, setStatus] = useState(event.status as EventStatus);

  const handleSubmit = (e: React.FormEvent): void => {
    e.preventDefault();
    if (!title.trim() || !start) return;
    updateEvent.mutate(
      {
        caseId,
        eventId: event.id,
        payload: {
          title: title.trim(),
          description: description.trim() || undefined,
          event_time_start: new Date(start).toISOString(),
          event_time_end: end ? new Date(end).toISOString() : undefined,
          time_precision: precision,
          status,
        },
      },
      { onSuccess: onDone },
    );
  };

  return (
    <form
      data-testid="event-edit-form"
      onSubmit={handleSubmit}
      className="mt-3 space-y-3"
    >
      <div>
        <label htmlFor="edit-title" className="text-muted-foreground text-xs">
          Title
        </label>
        <input
          id="edit-title"
          type="text"
          required
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className={inputClasses}
        />
      </div>
      <div>
        <label
          htmlFor="edit-description"
          className="text-muted-foreground text-xs"
        >
          Description
        </label>
        <textarea
          id="edit-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={3}
          className={inputClasses}
        />
      </div>
      <div>
        <label htmlFor="edit-start" className="text-muted-foreground text-xs">
          Start
        </label>
        <input
          id="edit-start"
          type="datetime-local"
          required
          value={start}
          onChange={(e) => setStart(e.target.value)}
          className={inputClasses}
        />
      </div>
      <div>
        <label htmlFor="edit-end" className="text-muted-foreground text-xs">
          End
        </label>
        <input
          id="edit-end"
          type="datetime-local"
          value={end}
          onChange={(e) => setEnd(e.target.value)}
          className={inputClasses}
        />
      </div>
      <div>
        <label
          htmlFor="edit-precision"
          className="text-muted-foreground text-xs"
        >
          Precision
        </label>
        <select
          id="edit-precision"
          value={precision}
          onChange={(e) => setPrecision(e.target.value)}
          className={inputClasses}
        >
          <option value="exact">exact</option>
          <option value="approximate">approximate</option>
          <option value="estimated">estimated</option>
        </select>
      </div>
      <div>
        <label htmlFor="edit-status" className="text-muted-foreground text-xs">
          Status
        </label>
        <select
          id="edit-status"
          value={status}
          onChange={(e) => setStatus(e.target.value as EventStatus)}
          className={inputClasses}
        >
          {EVENT_STATUSES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={updateEvent.isPending}
          className={
            'bg-primary rounded-md px-3 py-1.5 text-sm ' +
            'text-primary-foreground font-medium ' +
            'hover:bg-primary/90 disabled:opacity-50'
          }
        >
          {updateEvent.isPending ? 'Saving...' : 'Save'}
        </button>
        <button
          type="button"
          onClick={onDone}
          className={
            'border-border rounded-md border px-3 py-1.5 ' +
            'text-muted-foreground hover:bg-accent text-sm'
          }
        >
          Cancel
        </button>
      </div>
    </form>
  );
}

interface AddEvidenceFormProps {
  caseId: string;
  eventId: string;
  assets: Array<{ id: string; originalFilename: string }>;
  onDone: () => void;
}

function AddEvidenceForm(props: AddEvidenceFormProps): React.ReactElement {
  const { caseId, eventId, assets, onDone } = props;
  const linkEvidence = useLinkEvidence();

  const [assetId, setAssetId] = useState(assets[0]?.id ?? '');
  const [relationship, setRelationship] =
    useState<EvidenceRelationship>('supports');
  const [clipStart, setClipStart] = useState('');
  const [clipEnd, setClipEnd] = useState('');
  const [notes, setNotes] = useState('');

  const handleSubmit = (e: React.FormEvent): void => {
    e.preventDefault();
    if (!assetId) return;
    linkEvidence.mutate(
      {
        caseId,
        eventId,
        payload: {
          asset_id: assetId,
          relationship,
          ...(clipStart !== '' && { clip_start: Number(clipStart) }),
          ...(clipEnd !== '' && { clip_end: Number(clipEnd) }),
          ...(notes.trim() && { notes: notes.trim() }),
        },
      },
      { onSuccess: onDone },
    );
  };

  return (
    <form
      data-testid="add-evidence-form"
      onSubmit={handleSubmit}
      className="mt-3 space-y-3"
    >
      <div>
        <label
          htmlFor="evidence-asset"
          className="text-muted-foreground text-xs"
        >
          Asset
        </label>
        <select
          id="evidence-asset"
          required
          value={assetId}
          onChange={(e) => setAssetId(e.target.value)}
          className={inputClasses}
        >
          {assets.map((a) => (
            <option key={a.id} value={a.id}>
              {a.originalFilename}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label
          htmlFor="evidence-relationship"
          className="text-muted-foreground text-xs"
        >
          Relationship
        </label>
        <select
          id="evidence-relationship"
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
            htmlFor="evidence-clip-start"
            className="text-muted-foreground text-xs"
          >
            Clip start (s)
          </label>
          <input
            id="evidence-clip-start"
            type="number"
            min={0}
            step="any"
            value={clipStart}
            onChange={(e) => setClipStart(e.target.value)}
            className={inputClasses}
          />
        </div>
        <div className="flex-1">
          <label
            htmlFor="evidence-clip-end"
            className="text-muted-foreground text-xs"
          >
            Clip end (s)
          </label>
          <input
            id="evidence-clip-end"
            type="number"
            min={0}
            step="any"
            value={clipEnd}
            onChange={(e) => setClipEnd(e.target.value)}
            className={inputClasses}
          />
        </div>
      </div>
      <div>
        <label
          htmlFor="evidence-notes"
          className="text-muted-foreground text-xs"
        >
          Notes
        </label>
        <textarea
          id="evidence-notes"
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          className={inputClasses}
        />
      </div>
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={linkEvidence.isPending || !assetId}
          className={
            'bg-primary rounded-md px-3 py-1.5 text-sm ' +
            'text-primary-foreground font-medium ' +
            'hover:bg-primary/90 disabled:opacity-50'
          }
        >
          {linkEvidence.isPending ? 'Linking...' : 'Link evidence'}
        </button>
        <button
          type="button"
          onClick={onDone}
          className={
            'border-border rounded-md border px-3 py-1.5 ' +
            'text-muted-foreground hover:bg-accent text-sm'
          }
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
