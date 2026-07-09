import { useState } from 'react';
import { useParams } from 'react-router-dom';
import * as Tabs from '@radix-ui/react-tabs';
import { QueryError } from '@/components/layout/query-error';
import { ExportWizard } from '@/components/export/export-wizard';
import { ReportBuilder } from '@/components/export/report-builder';
import { ReportPreview } from '@/components/export/report-preview';
import { useDownloadExport, useExports } from '@/hooks/use-exports';

const STATUS_COLORS: Record<string, string> = {
  pending:
    'bg-yellow-100 text-yellow-800 ' +
    'dark:bg-yellow-900 dark:text-yellow-200',
  processing: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  complete: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
  failed: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200',
};

export function ExportPage(): React.ReactElement {
  const { caseId } = useParams<{ caseId: string }>();
  const safeId = caseId ?? '';
  const [wizardOpen, setWizardOpen] = useState(false);
  const { data, isLoading, isError, refetch } = useExports(safeId);
  const downloadExport = useDownloadExport(safeId);

  const exports = data?.items ?? [];

  return (
    <div className="space-y-6 p-6">
      <h1 className="text-foreground text-2xl font-bold">Exports</h1>

      <Tabs.Root defaultValue="bundle" data-testid="export-tabs">
        <Tabs.List className="border-border flex gap-1 border-b">
          <Tabs.Trigger
            value="bundle"
            data-testid="tab-bundle"
            className="text-muted-foreground hover:text-foreground data-[state=active]:border-primary data-[state=active]:text-foreground border-b-2 border-transparent px-4 py-2 text-sm font-medium transition-colors"
          >
            Export Bundle
          </Tabs.Trigger>
          <Tabs.Trigger
            value="report"
            data-testid="tab-report"
            className="text-muted-foreground hover:text-foreground data-[state=active]:border-primary data-[state=active]:text-foreground border-b-2 border-transparent px-4 py-2 text-sm font-medium transition-colors"
          >
            Evidence Report
          </Tabs.Trigger>
        </Tabs.List>

        {/* export bundle tab */}
        <Tabs.Content value="bundle" className="mt-4 space-y-4">
          <div className="flex justify-end">
            <button
              type="button"
              onClick={() => setWizardOpen(true)}
              className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-md px-4 py-2 text-sm"
              data-testid="new-export-btn"
            >
              New Export
            </button>
          </div>

          {isError && (
            <QueryError
              message="Failed to load exports."
              onRetry={() => void refetch()}
            />
          )}

          {isLoading && (
            <p className="text-muted-foreground text-sm">Loading exports...</p>
          )}

          {!isLoading && exports.length === 0 && (
            <p className="text-muted-foreground text-sm">
              No exports yet. Create one to get started.
            </p>
          )}

          {exports.length > 0 && (
            <div className="space-y-2">
              {exports.map((exp) => (
                <div
                  key={exp.id}
                  className="border-border flex items-center justify-between rounded-md border p-4"
                  data-testid={`export-row-${exp.id}`}
                >
                  <div>
                    <p className="text-foreground font-medium">{exp.name}</p>
                    <p className="text-muted-foreground text-xs">
                      {exp.format} — created{' '}
                      {new Date(exp.createdAt).toLocaleDateString()}
                    </p>
                  </div>
                  <div className="flex items-center gap-3">
                    <span
                      className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                        STATUS_COLORS[exp.status] ?? ''
                      }`}
                    >
                      {exp.status}
                    </span>
                    {exp.status === 'complete' && exp.storageKey && (
                      <button
                        type="button"
                        onClick={() => downloadExport.mutate(exp.id)}
                        disabled={downloadExport.isPending}
                        className="text-primary text-sm hover:underline disabled:opacity-50"
                        data-testid={`export-download-${exp.id}`}
                      >
                        {downloadExport.isPending &&
                        downloadExport.variables === exp.id
                          ? 'Preparing…'
                          : 'Download'}
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          <ExportWizard
            caseId={safeId}
            open={wizardOpen}
            onOpenChange={setWizardOpen}
          />
        </Tabs.Content>

        {/* evidence report tab */}
        <Tabs.Content value="report" className="mt-4">
          <div className="grid gap-6 lg:grid-cols-2">
            <ReportBuilder caseId={safeId} />
            <ReportPreview caseId={safeId} caseName="Case Report" />
          </div>
        </Tabs.Content>
      </Tabs.Root>
    </div>
  );
}
