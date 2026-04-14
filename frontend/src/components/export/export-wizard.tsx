import * as Dialog from '@radix-ui/react-dialog';
import { useState } from 'react';
import { useCreateExport } from '@/hooks/use-exports';
import type { CreateExportPayload } from '@/types/export';

interface ExportWizardProps {
  caseId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

type ExportFormat = 'zip' | 'pdf_report' | 'json_manifest';

const FORMAT_OPTIONS: {
  value: ExportFormat;
  label: string;
}[] = [
  { value: 'zip', label: 'ZIP Archive' },
  { value: 'pdf_report', label: 'PDF Report' },
  {
    value: 'json_manifest',
    label: 'JSON Manifest',
  },
];

export function ExportWizard(props: ExportWizardProps): React.ReactElement {
  const { caseId, open, onOpenChange } = props;
  const [step, setStep] = useState(1);
  const [name, setName] = useState('');
  const [format, setFormat] = useState<ExportFormat>('zip');
  const [includeOriginals, setIncludeOriginals] = useState(false);
  const [dateStart, setDateStart] = useState('');
  const [dateEnd, setDateEnd] = useState('');
  const createExport = useCreateExport(caseId);

  function reset(): void {
    setStep(1);
    setName('');
    setFormat('zip');
    setIncludeOriginals(false);
    setDateStart('');
    setDateEnd('');
  }

  function handleSubmit(): void {
    const payload: CreateExportPayload = {
      name: name.trim(),
      format,
      include_originals: includeOriginals,
    };
    if (dateStart) {
      payload.date_range_start = new Date(dateStart).toISOString();
    }
    if (dateEnd) {
      payload.date_range_end = new Date(dateEnd).toISOString();
    }

    createExport.mutate(payload, {
      onSuccess: () => {
        reset();
        onOpenChange(false);
      },
    });
  }

  function handleOpenChange(open: boolean): void {
    if (!open) reset();
    onOpenChange(open);
  }

  return (
    <Dialog.Root open={open} onOpenChange={handleOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content
          className="bg-card fixed left-1/2 top-1/2 w-full max-w-lg -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border p-6 shadow-lg"
          data-testid="export-wizard"
        >
          <Dialog.Title className="text-lg font-semibold text-foreground">
            Export Bundle — Step {step} of 3
          </Dialog.Title>
          <div aria-live="polite" className="sr-only">
            Step {step} of 3
          </div>
          <Dialog.Description className="mt-1 text-sm text-muted-foreground">
            Configure and generate an export bundle.
          </Dialog.Description>

          {step === 1 && (
            <div className="mt-4 space-y-3" data-testid="wizard-step-1">
              <label className="block">
                <span className="text-sm font-medium text-foreground">
                  Export Name
                </span>
                <input
                  type="text"
                  required
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                  placeholder="e.g. Case export 2026-03"
                />
              </label>

              <label className="block">
                <span className="text-sm font-medium text-foreground">
                  Format
                </span>
                <select
                  value={format}
                  onChange={(e) => setFormat(e.target.value as ExportFormat)}
                  className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                >
                  {FORMAT_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </label>

              <div className="flex justify-end">
                <button
                  type="button"
                  disabled={!name.trim()}
                  onClick={() => setStep(2)}
                  className="rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="mt-4 space-y-3" data-testid="wizard-step-2">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={includeOriginals}
                  onChange={(e) => setIncludeOriginals(e.target.checked)}
                  className="h-4 w-4 rounded border border-border"
                />
                <span className="text-sm text-foreground">
                  Include original files
                </span>
              </label>

              <label className="block">
                <span className="text-sm font-medium text-foreground">
                  Date Range Start
                </span>
                <input
                  type="date"
                  value={dateStart}
                  onChange={(e) => setDateStart(e.target.value)}
                  className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </label>

              <label className="block">
                <span className="text-sm font-medium text-foreground">
                  Date Range End
                </span>
                <input
                  type="date"
                  value={dateEnd}
                  onChange={(e) => setDateEnd(e.target.value)}
                  className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                />
              </label>

              <div className="flex justify-between">
                <button
                  type="button"
                  onClick={() => setStep(1)}
                  className="rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent"
                >
                  Back
                </button>
                <button
                  type="button"
                  onClick={() => setStep(3)}
                  className="rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground hover:bg-primary/90"
                >
                  Next
                </button>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="mt-4 space-y-3" data-testid="wizard-step-3">
              <div className="rounded-md border border-border p-3 text-sm">
                <p>
                  <strong>Name:</strong> {name}
                </p>
                <p>
                  <strong>Format:</strong>{' '}
                  {FORMAT_OPTIONS.find((o) => o.value === format)?.label}
                </p>
                <p>
                  <strong>Include Originals:</strong>{' '}
                  {includeOriginals ? 'Yes' : 'No'}
                </p>
                {dateStart && (
                  <p>
                    <strong>Date Start:</strong> {dateStart}
                  </p>
                )}
                {dateEnd && (
                  <p>
                    <strong>Date End:</strong> {dateEnd}
                  </p>
                )}
              </div>

              <div className="flex justify-between">
                <button
                  type="button"
                  onClick={() => setStep(2)}
                  className="rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent"
                >
                  Back
                </button>
                <button
                  type="button"
                  disabled={createExport.isPending}
                  onClick={handleSubmit}
                  data-testid="export-submit"
                  className="rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                >
                  {createExport.isPending ? 'Exporting...' : 'Create Export'}
                </button>
              </div>
            </div>
          )}
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
