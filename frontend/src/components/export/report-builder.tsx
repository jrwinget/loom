import { useCallback, useState } from 'react';
import { useCreateExport } from '@/hooks/use-exports';
import { useTimelineEvents } from '@/hooks/use-timeline';
import type { CreateExportPayload } from '@/types/export';

interface ReportBuilderProps {
  caseId: string;
}

export function ReportBuilder(props: ReportBuilderProps): React.ReactElement {
  const { caseId } = props;

  const [dateStart, setDateStart] = useState('');
  const [dateEnd, setDateEnd] = useState('');
  const [allEvents, setAllEvents] = useState(true);
  const [selectedEventIds, setSelectedEventIds] = useState<Set<string>>(
    new Set(),
  );
  const [includeEvidence, setIncludeEvidence] = useState(true);
  const [includeContradictions, setIncludeContradictions] = useState(true);
  const [includeCustody, setIncludeCustody] = useState(false);
  const [summary, setSummary] = useState('');

  const { data: eventsData } = useTimelineEvents(caseId);
  const createExport = useCreateExport(caseId);

  const events = eventsData?.items ?? [];

  const toggleEvent = useCallback((id: string) => {
    setSelectedEventIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const handleSubmit = useCallback(() => {
    const payload: CreateExportPayload = {
      name: `Evidence Report ${new Date().toISOString().slice(0, 10)}`,
      format: 'pdf_report',
      include_evidence: includeEvidence,
      include_contradictions: includeContradictions,
      include_custody: includeCustody,
    };

    if (dateStart) {
      payload.date_range_start = new Date(dateStart).toISOString();
    }
    if (dateEnd) {
      payload.date_range_end = new Date(dateEnd).toISOString();
    }
    if (!allEvents && selectedEventIds.size > 0) {
      payload.event_ids = Array.from(selectedEventIds);
    }
    if (summary.trim()) {
      payload.executive_summary = summary.trim();
    }

    createExport.mutate(payload);
  }, [
    dateStart,
    dateEnd,
    allEvents,
    selectedEventIds,
    includeEvidence,
    includeContradictions,
    includeCustody,
    summary,
    createExport,
  ]);

  return (
    <div data-testid="report-builder" className="space-y-6">
      {/* date range */}
      <fieldset className="space-y-2">
        <legend className="text-foreground text-sm font-medium">
          Date Range
        </legend>
        <div className="flex gap-3">
          <label className="block flex-1">
            <span className="text-muted-foreground text-xs">Start</span>
            <input
              type="date"
              value={dateStart}
              onChange={(e) => setDateStart(e.target.value)}
              data-testid="report-date-start"
              className="border-border bg-background text-foreground mt-1 block w-full rounded-md border px-3 py-2 text-sm"
            />
          </label>
          <label className="block flex-1">
            <span className="text-muted-foreground text-xs">End</span>
            <input
              type="date"
              value={dateEnd}
              onChange={(e) => setDateEnd(e.target.value)}
              data-testid="report-date-end"
              className="border-border bg-background text-foreground mt-1 block w-full rounded-md border px-3 py-2 text-sm"
            />
          </label>
        </div>
      </fieldset>

      {/* event selection */}
      <fieldset className="space-y-2">
        <legend className="text-foreground text-sm font-medium">Events</legend>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={allEvents}
            onChange={(e) => setAllEvents(e.target.checked)}
            className="border-border h-4 w-4 rounded"
          />
          <span className="text-foreground text-sm">All events</span>
        </label>
        {!allEvents && (
          <div
            className="border-border max-h-40 space-y-1 overflow-y-auto rounded border p-2"
            data-testid="event-checkboxes"
          >
            {events.map((event) => (
              <label key={event.id} className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={selectedEventIds.has(event.id)}
                  onChange={() => toggleEvent(event.id)}
                  className="border-border h-4 w-4 rounded"
                />
                <span className="text-foreground text-sm">{event.title}</span>
              </label>
            ))}
          </div>
        )}
      </fieldset>

      {/* section toggles */}
      <fieldset className="space-y-2">
        <legend className="text-foreground text-sm font-medium">
          Include Sections
        </legend>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={includeEvidence}
            onChange={(e) => setIncludeEvidence(e.target.checked)}
            className="border-border h-4 w-4 rounded"
          />
          <span className="text-foreground text-sm">Evidence</span>
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={includeContradictions}
            onChange={(e) => setIncludeContradictions(e.target.checked)}
            className="border-border h-4 w-4 rounded"
          />
          <span className="text-foreground text-sm">Contradictions</span>
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={includeCustody}
            onChange={(e) => setIncludeCustody(e.target.checked)}
            className="border-border h-4 w-4 rounded"
          />
          <span className="text-foreground text-sm">Chain of Custody</span>
        </label>
      </fieldset>

      {/* executive summary */}
      <fieldset className="space-y-2">
        <legend className="text-foreground text-sm font-medium">
          Executive Summary
        </legend>
        <textarea
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          data-testid="report-summary"
          placeholder="Brief overview of the case and key findings..."
          rows={4}
          className="border-border bg-background text-foreground placeholder:text-muted-foreground block w-full rounded-md border px-3 py-2 text-sm"
        />
      </fieldset>

      {/* submit */}
      <button
        type="button"
        data-testid="generate-report-btn"
        onClick={handleSubmit}
        disabled={createExport.isPending}
        className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-md px-4 py-2 text-sm disabled:opacity-50"
      >
        {createExport.isPending ? 'Generating...' : 'Generate Report'}
      </button>

      {createExport.isSuccess && (
        <p data-testid="report-success" className="text-sm text-green-600">
          Report generation started. Check exports for status.
        </p>
      )}
    </div>
  );
}
