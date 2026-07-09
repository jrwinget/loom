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
      <div className="border-border border-b pb-3">
        <h2 className="text-foreground text-xl font-bold">{caseName}</h2>
        <p className="text-muted-foreground text-xs">Evidence Report Preview</p>
      </div>

      {/* event list */}
      {isLoading && (
        <p className="text-muted-foreground text-sm">Loading preview...</p>
      )}

      {!isLoading && events.length === 0 && (
        <p className="text-muted-foreground text-sm">
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
                className="border-border rounded border p-3"
              >
                <h3 className="text-foreground text-sm font-semibold">
                  {event.title}
                </h3>
                <p className="text-muted-foreground text-xs">
                  {supporting} supporting, {contradicting} contradicting
                </p>
              </div>
            );
          })}
        </div>
      )}

      {/* disclaimer */}
      <p className="bg-muted text-muted-foreground rounded p-3 text-xs">
        This is a preview. Generate PDF for the full report.
      </p>
    </div>
  );
}
