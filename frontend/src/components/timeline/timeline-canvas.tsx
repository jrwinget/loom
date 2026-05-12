import type { TimelineEvent } from '@/types/timeline';
import { TimelineEventCard } from './timeline-event';

interface TimelineCanvasProps {
  events: TimelineEvent[];
  selectedEventId: string | null;
  onSelectEvent: (event: TimelineEvent) => void;
  loading?: boolean;
}

function SkeletonBlock(): React.ReactElement {
  return (
    <div
      data-testid="skeleton-event"
      className="h-28 animate-pulse rounded-lg bg-muted"
    />
  );
}

export function TimelineCanvas(props: TimelineCanvasProps): React.ReactElement {
  const { events, selectedEventId, onSelectEvent, loading = false } = props;

  if (loading) {
    return (
      <div
        data-testid="timeline-canvas"
        aria-busy="true"
        aria-label="Loading timeline events"
        className="flex gap-4 overflow-x-auto p-4"
      >
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="min-w-[220px]">
            <SkeletonBlock />
          </div>
        ))}
      </div>
    );
  }

  if (events.length === 0) {
    return (
      <div
        data-testid="timeline-canvas"
        className="flex h-64 items-center justify-center rounded-lg border border-dashed border-border"
      >
        <p className="text-sm text-muted-foreground">
          No events on this timeline yet
        </p>
      </div>
    );
  }

  return (
    <div data-testid="timeline-canvas" className="relative">
      {/* horizontal axis line */}
      <div className="absolute left-0 right-0 top-1/2 h-0.5 bg-border" />

      {/* events laid out horizontally */}
      <div className="flex gap-4 overflow-x-auto px-4 py-8">
        {events.map((event) => (
          <div
            key={event.id}
            className="min-w-[220px] max-w-[280px] flex-shrink-0"
          >
            <TimelineEventCard
              event={event}
              selected={selectedEventId === event.id}
              onClick={onSelectEvent}
            />
          </div>
        ))}
      </div>
    </div>
  );
}
