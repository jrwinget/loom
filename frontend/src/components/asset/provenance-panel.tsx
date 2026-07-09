import { useState } from 'react';
import { useAssetProvenance } from '@/hooks/use-provenance';
import type { ProvenanceRecord } from '@/types/provenance';

interface ProvenancePanelProps {
  caseId: string;
  assetId: string;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

interface ActionItemProps {
  action: Record<string, unknown>;
}

function ActionItem({ action }: ActionItemProps): React.ReactElement {
  return (
    <div className="flex items-start gap-3" data-testid="action-item">
      <div className="bg-primary mt-1 h-2 w-2 shrink-0 rounded-full" />
      <div>
        <p className="text-foreground text-xs font-medium">
          {String(action.action ?? 'unknown')}
        </p>
        {typeof action.when === 'string' && (
          <p className="text-muted-foreground text-xs">
            {formatDate(String(action.when))}
          </p>
        )}
      </div>
    </div>
  );
}

interface RecordCardProps {
  record: ProvenanceRecord;
}

function RecordCard({ record }: RecordCardProps): React.ReactElement {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      data-testid="provenance-record"
      className="border-border rounded-md border p-3"
    >
      <div className="mb-2 flex items-center justify-between">
        <span className="text-foreground text-xs font-semibold">
          {record.claimGenerator}
        </span>
        <span className="text-muted-foreground text-xs">
          {formatDate(record.createdAt)}
        </span>
      </div>

      {/* actions list */}
      <div className="mb-2 space-y-2">
        {record.actions.map((action, i) => (
          <ActionItem key={i} action={action} />
        ))}
      </div>

      {/* expandable manifest data */}
      <button
        data-testid="toggle-manifest"
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="text-primary text-xs font-medium hover:underline"
      >
        {expanded ? 'Hide manifest' : 'Show manifest'}
      </button>

      {expanded && (
        <pre
          data-testid="manifest-json"
          className="bg-muted mt-2 max-h-60 overflow-auto rounded p-2 text-xs"
        >
          {JSON.stringify(record.manifestData, null, 2)}
        </pre>
      )}
    </div>
  );
}

export function ProvenancePanel({
  caseId,
  assetId,
}: ProvenancePanelProps): React.ReactElement {
  const { data, isLoading } = useAssetProvenance(caseId, assetId);

  if (isLoading) {
    return (
      <div data-testid="provenance-loading" className="p-4 text-sm">
        Loading provenance data...
      </div>
    );
  }

  const records = data?.items ?? [];

  if (records.length === 0) {
    return (
      <div data-testid="provenance-empty" className="p-4">
        <p className="text-muted-foreground text-sm">No provenance data yet</p>
      </div>
    );
  }

  return (
    <div data-testid="provenance-panel" className="flex flex-col gap-3 p-4">
      <h3 className="text-foreground text-sm font-semibold">
        Provenance records
      </h3>
      {records.map((record) => (
        <RecordCard key={record.id} record={record} />
      ))}
    </div>
  );
}
