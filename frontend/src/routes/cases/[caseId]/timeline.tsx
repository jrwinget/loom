import { useCallback, useState } from 'react';
import { useParams } from 'react-router-dom';
import { QueryError } from '@/components/layout/query-error';
import { TimelineCanvas } from '@/components/timeline/timeline-canvas';
import { TimelineControls } from '@/components/timeline/timeline-controls';
import { useTimelineEvents, useCreateEvent } from '@/hooks/use-timeline';
import type {
  CreateEventPayload,
  EventStatus,
  TimelineEvent,
  ZoomLevel,
} from '@/types/timeline';

export function TimelinePage(): React.ReactElement {
  const { caseId } = useParams<{ caseId: string }>();
  const safeId = caseId ?? '';

  const [statusFilter, setStatusFilter] = useState<EventStatus | 'all'>('all');
  const [zoomLevel, setZoomLevel] = useState<ZoomLevel>('days');
  const [selectedEvent, setSelectedEvent] = useState<TimelineEvent | null>(
    null,
  );
  const [showAddForm, setShowAddForm] = useState(false);

  const filterParam = statusFilter === 'all' ? undefined : statusFilter;

  const { data, isLoading, isError, refetch } = useTimelineEvents(
    safeId,
    filterParam,
  );

  const createEvent = useCreateEvent();

  const handleAddEvent = useCallback(() => {
    setShowAddForm((prev) => !prev);
  }, []);

  const handleSubmitEvent = useCallback(
    (payload: CreateEventPayload) => {
      createEvent.mutate(
        { caseId: safeId, payload },
        {
          onSuccess: () => {
            setShowAddForm(false);
          },
        },
      );
    },
    [createEvent, safeId],
  );

  const handleSelectEvent = useCallback(
    (event: TimelineEvent) => {
      setSelectedEvent(selectedEvent?.id === event.id ? null : event);
    },
    [selectedEvent],
  );

  const handleClosePanel = useCallback(() => {
    setSelectedEvent(null);
  }, []);

  return (
    <div className="flex flex-col gap-4 p-6">
      <h1 className="text-2xl font-bold text-foreground">Timeline</h1>

      <TimelineControls
        onAddEvent={handleAddEvent}
        statusFilter={statusFilter}
        onStatusFilterChange={setStatusFilter}
        zoomLevel={zoomLevel}
        onZoomChange={setZoomLevel}
      />

      {showAddForm && (
        <AddEventForm
          onSubmit={handleSubmitEvent}
          onCancel={() => setShowAddForm(false)}
          submitting={createEvent.isPending}
        />
      )}

      {isError && (
        <QueryError
          message="Failed to load timeline events."
          onRetry={() => void refetch()}
        />
      )}

      {!isError && (
        <TimelineCanvas
          events={data?.items ?? []}
          selectedEventId={selectedEvent?.id ?? null}
          onSelectEvent={handleSelectEvent}
          loading={isLoading}
        />
      )}

      {selectedEvent && (
        <>
          <button
            type="button"
            className="fixed inset-0 z-30 bg-black/30"
            onClick={handleClosePanel}
            aria-label="Close panel"
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="event-detail-title"
            data-testid="event-detail-panel"
            className={
              'fixed inset-y-0 right-0 z-40 flex w-full ' +
              'max-w-md flex-col overflow-y-auto border-l' +
              'border-border bg-background p-6 shadow-lg'
            }
          >
            <h2
              id="event-detail-title"
              className="text-lg font-semibold text-foreground"
            >
              {selectedEvent.title}
            </h2>
            {selectedEvent.description && (
              <p className="mt-2 text-sm text-muted-foreground">
                {selectedEvent.description}
              </p>
            )}
            <div className={'mt-4 space-y-2 text-sm text-muted-foreground'}>
              <p>
                Status:{' '}
                <span className="font-medium">{selectedEvent.status}</span>
              </p>
              <p>
                Precision:{' '}
                <span className="font-medium">
                  {selectedEvent.timePrecision}
                </span>
              </p>
              <p>
                Evidence:{' '}
                <span className="font-medium">
                  {selectedEvent.evidenceCount} link
                  {selectedEvent.evidenceCount !== 1 ? 's' : ''}
                </span>
              </p>
              {selectedEvent.hasContradictions && (
                <p className="font-medium text-amber-600">
                  Has contradicting evidence
                </p>
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}

interface AddEventFormProps {
  onSubmit: (payload: CreateEventPayload) => void;
  onCancel: () => void;
  submitting: boolean;
}

function AddEventForm(props: AddEventFormProps): React.ReactElement {
  const { onSubmit, onCancel, submitting } = props;
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [occurredAt, setOccurredAt] = useState('');

  const handleSubmit = (e: React.FormEvent): void => {
    e.preventDefault();
    if (!title.trim() || !occurredAt) return;
    onSubmit({
      title: title.trim(),
      description: description.trim() || undefined,
      event_time_start: new Date(occurredAt).toISOString(),
    });
  };

  return (
    <form
      data-testid="add-event-form"
      onSubmit={handleSubmit}
      className={'bg-card rounded-lg border border-border p-4 ' + 'space-y-3'}
    >
      <h3 className="text-sm font-semibold text-foreground">New Event</h3>
      <div>
        <label htmlFor="event-title" className="text-xs text-muted-foreground">
          Title
        </label>
        <input
          id="event-title"
          type="text"
          required
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          className={
            'mt-1 w-full rounded-md border border-border ' +
            'bg-background px-3 py-1.5 text-sm text-foreground'
          }
        />
      </div>
      <div>
        <label
          htmlFor="event-description"
          className="text-xs text-muted-foreground"
        >
          Description
        </label>
        <textarea
          id="event-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          rows={3}
          className={
            'mt-1 w-full rounded-md border border-border ' +
            'bg-background px-3 py-1.5 text-sm text-foreground'
          }
        />
      </div>
      <div>
        <label
          htmlFor="event-occurred-at"
          className="text-xs text-muted-foreground"
        >
          Occurred at
        </label>
        <input
          id="event-occurred-at"
          type="datetime-local"
          required
          value={occurredAt}
          onChange={(e) => setOccurredAt(e.target.value)}
          className={
            'mt-1 w-full rounded-md border border-border ' +
            'bg-background px-3 py-1.5 text-sm text-foreground'
          }
        />
      </div>
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={submitting}
          className={
            'rounded-md bg-primary px-3 py-1.5 text-sm ' +
            'font-medium text-primary-foreground' +
            'hover:bg-primary/90 disabled:opacity-50'
          }
        >
          {submitting ? 'Creating...' : 'Create Event'}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className={
            'rounded-md border border-border px-3 py-1.5 ' +
            'text-sm text-muted-foreground hover:bg-accent'
          }
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
