import { useCallback, useState } from 'react';
import { useParams } from 'react-router-dom';
import { TimelineCanvas } from
  '@/components/timeline/timeline-canvas';
import { TimelineControls } from
  '@/components/timeline/timeline-controls';
import { useTimelineEvents } from
  '@/hooks/use-timeline';
import type {
  EventStatus,
  TimelineEvent,
  ZoomLevel,
} from '@/types/timeline';

export function TimelinePage(): React.ReactElement {
  const { caseId } = useParams<{ caseId: string }>();
  const safeId = caseId ?? '';

  const [statusFilter, setStatusFilter] = useState<
    EventStatus | 'all'
  >('all');
  const [zoomLevel, setZoomLevel] =
    useState<ZoomLevel>('days');
  const [selectedEvent, setSelectedEvent] =
    useState<TimelineEvent | null>(null);

  const filterParam =
    statusFilter === 'all'
      ? undefined
      : statusFilter;

  const { data, isLoading } = useTimelineEvents(
    safeId,
    filterParam,
  );

  const handleAddEvent = useCallback(() => {
    // placeholder for add event modal
  }, []);

  const handleSelectEvent = useCallback(
    (event: TimelineEvent) => {
      setSelectedEvent(
        selectedEvent?.id === event.id
          ? null
          : event,
      );
    },
    [selectedEvent],
  );

  const handleClosePanel = useCallback(() => {
    setSelectedEvent(null);
  }, []);

  return (
    <div className="flex flex-col gap-4 p-6">
      <h1 className="text-2xl font-bold
        text-foreground">
        Timeline
      </h1>

      {/* controls */}
      <TimelineControls
        onAddEvent={handleAddEvent}
        statusFilter={statusFilter}
        onStatusFilterChange={setStatusFilter}
        zoomLevel={zoomLevel}
        onZoomChange={setZoomLevel}
      />

      {/* canvas */}
      <TimelineCanvas
        events={data?.items ?? []}
        selectedEventId={selectedEvent?.id ?? null}
        onSelectEvent={handleSelectEvent}
        loading={isLoading}
      />

      {/* event detail panel */}
      {selectedEvent && (
        <>
          <button
            type="button"
            className="fixed inset-0 z-30
              bg-black/30"
            onClick={handleClosePanel}
            aria-label="Close panel"
          />
          <div
            data-testid="event-detail-panel"
            className="fixed inset-y-0 right-0 z-40
              flex w-full max-w-md flex-col
              overflow-y-auto border-l border-border
              bg-background p-6 shadow-lg"
          >
            <h2 className="text-lg font-semibold
              text-foreground">
              {selectedEvent.title}
            </h2>
            {selectedEvent.description && (
              <p className="mt-2 text-sm
                text-muted-foreground">
                {selectedEvent.description}
              </p>
            )}
            <div className="mt-4 space-y-2 text-sm
              text-muted-foreground">
              <p>
                Status:{' '}
                <span className="font-medium">
                  {selectedEvent.status}
                </span>
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
                  {selectedEvent.evidenceCount !== 1
                    ? 's'
                    : ''}
                </span>
              </p>
              {selectedEvent.hasContradictions && (
                <p className="text-amber-600
                  font-medium">
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
