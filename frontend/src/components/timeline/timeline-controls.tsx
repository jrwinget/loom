import type { EventStatus, ZoomLevel } from '@/types/timeline';

interface TimelineControlsProps {
  onAddEvent: () => void;
  statusFilter: EventStatus | 'all';
  onStatusFilterChange: (status: EventStatus | 'all') => void;
  zoomLevel: ZoomLevel;
  onZoomChange: (zoom: ZoomLevel) => void;
  // correlation confidence threshold in [0, 1]. when set, the
  // timeline page filters its probable-match overlay to candidates
  // whose confidence is at least this value.
  confidenceThreshold?: number;
  onConfidenceThresholdChange?: (value: number) => void;
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
    confidenceThreshold,
    onConfidenceThresholdChange,
  } = props;

  return (
    <div
      data-testid="timeline-controls"
      className="flex flex-wrap items-center gap-3 rounded-lg border border-border bg-card p-3"
    >
      {/* add event button */}
      <button
        type="button"
        data-testid="add-event-btn"
        className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
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
          className="rounded-md border border-input bg-background px-2 py-1 text-xs"
          value={statusFilter}
          onChange={(e) =>
            onStatusFilterChange(e.target.value as EventStatus | 'all')
          }
        >
          {statusOptions.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>

      {/* correlation confidence threshold */}
      {confidenceThreshold !== undefined && onConfidenceThresholdChange && (
        <div className="flex items-center gap-1.5">
          <label
            htmlFor="correlation-threshold"
            className="text-xs text-muted-foreground"
          >
            Correlation ≥
          </label>
          <input
            id="correlation-threshold"
            data-testid="correlation-threshold"
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={confidenceThreshold}
            onChange={(e) =>
              onConfidenceThresholdChange(Number(e.target.value))
            }
            className="h-1 w-24 cursor-pointer"
            aria-valuemin={0}
            aria-valuemax={1}
            aria-valuenow={confidenceThreshold}
          />
          <span
            data-testid="correlation-threshold-value"
            className="text-xs tabular-nums text-muted-foreground"
          >
            {Math.round(confidenceThreshold * 100)}%
          </span>
        </div>
      )}

      {/* zoom control */}
      <div className="ml-auto flex items-center gap-1.5">
        <label htmlFor="zoom-level" className="text-xs text-muted-foreground">
          Zoom:
        </label>
        <select
          id="zoom-level"
          data-testid="zoom-level"
          className="rounded-md border border-input bg-background px-2 py-1 text-xs"
          value={zoomLevel}
          onChange={(e) => onZoomChange(e.target.value as ZoomLevel)}
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
