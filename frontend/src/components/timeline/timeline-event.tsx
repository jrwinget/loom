import React from 'react';
import type { TimelineEvent as TEvent } from '@/types/timeline';

interface TimelineEventProps {
  event: TEvent;
  selected: boolean;
  onClick: (event: TEvent) => void;
  onConflictClick?: (event: TEvent) => void;
}

const statusColors: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-800 dark:bg-gray-900 ' + 'dark:text-gray-200',
  proposed:
    'bg-blue-100 text-blue-800 dark:bg-blue-900 ' + 'dark:text-blue-200',
  accepted:
    'bg-green-100 text-green-800 dark:bg-green-900 ' + 'dark:text-green-200',
  rejected: 'bg-red-100 text-red-800 dark:bg-red-900 ' + 'dark:text-red-200',
};

function formatTime(iso: string): string {
  return new Date(iso).toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export const TimelineEventCard = React.memo(function TimelineEventCard(
  props: TimelineEventProps,
): React.ReactElement {
  const { event, selected, onClick, onConflictClick } = props;
  const colorClass = statusColors[event.status] ?? statusColors['draft'];

  const timeRange = event.eventTimeEnd
    ? `${formatTime(event.eventTimeStart)} - ${formatTime(event.eventTimeEnd)}`
    : formatTime(event.eventTimeStart);

  return (
    <button
      type="button"
      data-testid={`timeline-event-${event.id}`}
      data-status={event.status}
      className={`flex w-full flex-col rounded-lg border p-3 text-left shadow-sm transition-colors ${
        selected
          ? 'border-primary bg-accent/50'
          : 'bg-card border-border hover:bg-accent/30'
      }`}
      onClick={() => onClick(event)}
    >
      {/* header */}
      <div className="flex items-start justify-between">
        <h4 className="text-sm font-semibold text-foreground">{event.title}</h4>
        <div className="flex items-center gap-1.5">
          {event.hasContradictions && (
            <span
              role="button"
              tabIndex={0}
              data-testid="contradiction-indicator"
              className="cursor-pointer text-amber-500 hover:text-amber-600"
              title="Has contradicting evidence"
              aria-label="Has contradicting evidence"
              onClick={(e) => {
                e.stopPropagation();
                onConflictClick?.(event);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.stopPropagation();
                  onConflictClick?.(event);
                }
              }}
            >
              &#9888;
            </span>
          )}
          <span
            data-testid="event-status-badge"
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${colorClass}`}
          >
            {event.status}
          </span>
        </div>
      </div>

      {/* time range */}
      <p className="mt-1 text-xs text-muted-foreground">{timeRange}</p>

      {/* precision label */}
      <span className="mt-0.5 text-xs italic text-muted-foreground">
        {event.timePrecision}
      </span>

      {/* location if present */}
      {event.locationDescription && (
        <p className="mt-1 text-xs text-muted-foreground">
          {event.locationDescription}{' '}
          <span className="italic">({event.locationConfidence})</span>
        </p>
      )}

      {/* evidence count */}
      <div className="mt-2 text-xs text-muted-foreground">
        {event.evidenceCount} evidence link
        {event.evidenceCount !== 1 ? 's' : ''}
      </div>
    </button>
  );
});
