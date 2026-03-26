import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { ExportWizard } from
  '@/components/export/export-wizard';
import { useExports } from '@/hooks/use-exports';

const STATUS_COLORS: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800',
  processing: 'bg-blue-100 text-blue-800',
  complete: 'bg-green-100 text-green-800',
  failed: 'bg-red-100 text-red-800',
};

export function ExportPage(): React.ReactElement {
  const { caseId } = useParams<{ caseId: string }>();
  const [wizardOpen, setWizardOpen] = useState(false);
  const { data, isLoading } = useExports(
    caseId ?? '',
  );

  const exports = data?.items ?? [];

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <h1
          className="text-2xl font-bold text-foreground"
        >
          Exports
        </h1>
        <button
          type="button"
          onClick={() => setWizardOpen(true)}
          className="rounded-md bg-primary px-4 py-2
            text-sm text-primary-foreground
            hover:bg-primary/90"
          data-testid="new-export-btn"
        >
          New Export
        </button>
      </div>

      {isLoading && (
        <p className="text-sm text-muted-foreground">
          Loading exports...
        </p>
      )}

      {!isLoading && exports.length === 0 && (
        <p className="text-sm text-muted-foreground">
          No exports yet. Create one to get started.
        </p>
      )}

      {exports.length > 0 && (
        <div className="space-y-2">
          {exports.map((exp) => (
            <div
              key={exp.id}
              className="flex items-center justify-between
                rounded-md border border-border p-4"
              data-testid={`export-row-${exp.id}`}
            >
              <div>
                <p
                  className="font-medium text-foreground"
                >
                  {exp.name}
                </p>
                <p
                  className="text-xs text-muted-foreground"
                >
                  {exp.format} — created{' '}
                  {new Date(
                    exp.createdAt,
                  ).toLocaleDateString()}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <span
                  className={`rounded-full px-2 py-0.5
                    text-xs font-medium ${
                      STATUS_COLORS[exp.status] ?? ''
                    }`}
                >
                  {exp.status}
                </span>
                {exp.status === 'complete' &&
                  exp.storageKey && (
                    <a
                      href={exp.storageKey}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-sm text-primary
                        hover:underline"
                    >
                      Download
                    </a>
                  )}
              </div>
            </div>
          ))}
        </div>
      )}

      <ExportWizard
        caseId={caseId ?? ''}
        open={wizardOpen}
        onOpenChange={setWizardOpen}
      />
    </div>
  );
}
