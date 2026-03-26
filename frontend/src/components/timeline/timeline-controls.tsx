import type { EventStatus, ZoomLevel } from
  '@/types/timeline';

interface TimelineControlsProps {
  onAddEvent: () => void;
  statusFilter: EventStatus | 'all';
  onStatusFilterChange: (
    status: EventStatus | 'all',
  ) => void;
  zoomLevel: ZoomLevel;
  onZoomChange: (zoom: ZoomLevel) => void;
}

const statusOptions: Array<{
  value: EventStatus | 'all';
  label: string;
}> = [
  { value: 'all', label: 'All' },
  { value: 'draft', label: 'Draft' },
  { value: 'proposed', label: 'Proposed' },
  { value: 'accepted', label: 'Accepted' },
  { value: 'rejected', label: 'Rejected' },
];

const zoomOptions: Array<{
  value: ZoomLevel;
  label: string;
}> = [
  { value: 'hours', label: 'Hours' },
  { value: 'days', label: 'Days' },
  { value: 'weeks', label: 'Weeks' },
];

export function TimelineControls(
  props: TimelineControlsProps,
): React.ReactElement {
  const {
    onAddEvent,
    statusFilter,
    onStatusFilterChange,
    zoomLevel,
    onZoomChange,
  } = props;

  return (
    <div
      data-testid="timeline-controls"
      className="flex flex-wrap items-center gap-3
        rounded-lg border border-border bg-card p-3"
    >
      {/* add event button */}
      <button
        type="button"
        data-testid="add-event-btn"
        className="rounded-md bg-primary px-3 py-1.5
          text-sm font-medium text-primary-foreground
          hover:bg-primary/90"
        onClick={onAddEvent}
      >
        Add Event
      </button>

      {/* status filter */}
      <div className="flex items-center gap-1.5">
        <label
          htmlFor="status-filter"
          className="text-xs text-muted-foreground"
        >
          Status:
        </label>
        <select
          id="status-filter"
          data-testid="status-filter"
          className="rounded-md border border-input
            bg-background px-2 py-1 text-xs"
          value={statusFilter}
          onChange={(e) =>
            onStatusFilterChange(
              e.target.value as EventStatus | 'all',
            )
          }
        >
          {statusOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* zoom control */}
      <div className="flex items-center gap-1.5
        ml-auto">
        <label
          htmlFor="zoom-level"
          className="text-xs text-muted-foreground"
        >
          Zoom:
        </label>
        <select
          id="zoom-level"
          data-testid="zoom-level"
          className="rounded-md border border-input
            bg-background px-2 py-1 text-xs"
          value={zoomLevel}
          onChange={(e) =>
            onZoomChange(
              e.target.value as ZoomLevel,
            )
          }
        >
          {zoomOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}
