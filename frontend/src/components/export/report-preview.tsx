import { useTimeline } from '@/hooks/use-timeline';

interface ReportPreviewProps {
  caseId: string;
  caseName: string;
}

export function ReportPreview(props: ReportPreviewProps): React.ReactElement {
  const { caseId, caseName } = props;
  const { data, isLoading } = useTimeline(caseId);

  const events = data?.events ?? [];

  return (
    <div data-testid="report-preview" className="space-y-4">
      {/* case header */}
      <div className="border-b border-border pb-3">
        <h2 className="text-xl font-bold text-foreground">{caseName}</h2>
        <p className="text-xs text-muted-foreground">Evidence Report Preview</p>
      </div>

      {/* event list */}
      {isLoading && (
        <p className="text-sm text-muted-foreground">Loading preview...</p>
      )}

      {!isLoading && events.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No events to include in the report.
        </p>
      )}

      {events.length > 0 && (
        <div className="space-y-2">
          {events.map((event) => {
            const supporting = event.evidence.filter(
              (e) => e.relationship === 'supports',
            ).length;
            const contradicting = event.evidence.filter(
              (e) => e.relationship === 'contradicts',
            ).length;

            return (
              <div
                key={event.id}
                data-testid={`preview-event-${event.id}`}
                className="rounded border border-border p-3"
              >
                <h3 className="text-sm font-semibold text-foreground">
                  {event.title}
                </h3>
                <p className="text-xs text-muted-foreground">
                  {supporting} supporting, {contradicting} contradicting
                </p>
              </div>
            );
          })}
        </div>
      )}

      {/* disclaimer */}
      <p className="rounded bg-muted p-3 text-xs text-muted-foreground">
        This is a preview. Generate PDF for the full report.
      </p>
    </div>
  );
}
