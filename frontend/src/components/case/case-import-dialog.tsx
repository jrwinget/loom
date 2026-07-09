import { useRef, useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { useNavigate } from 'react-router-dom';
import {
  useImportBundle,
  type ImportBundleResult,
} from '@/hooks/use-import-bundle';
import { useJobStore } from '@/stores/job-store';
import { useToastStore } from '@/stores/toast-store';

const SIGNATURE_COPY: Record<ImportBundleResult['signatureStatus'], string> = {
  signed_trusted: 'Signature verified against a trusted key.',
  signed_untrusted:
    'Signed, but by a key this install does not trust — imported, ' +
    'and the unverified source is recorded in the custody log.',
  unsigned: 'This bundle was not signed.',
};

export function CaseImportDialog(props: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}): React.ReactElement {
  const { open, onOpenChange } = props;
  const [file, setFile] = useState<File | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const { importing, progress, error, run, reset } = useImportBundle();
  const registerJob = useJobStore((s) => s.registerJob);
  const addToast = useToastStore.getState().addToast;
  const navigate = useNavigate();

  const close = (): void => {
    setFile(null);
    reset();
    onOpenChange(false);
  };

  const handleImport = async (): Promise<void> => {
    if (!file) return;
    const result = await run(file);
    if (!result) return;

    // the case exists immediately; the contents fill in via the job
    registerJob({
      workflowId: result.workflowId,
      caseId: result.caseId,
      kind: 'bundle_import',
      label: file.name,
    });
    addToast({
      type: result.signatureStatus === 'signed_trusted' ? 'success' : 'info',
      message: SIGNATURE_COPY[result.signatureStatus],
    });
    navigate(`/cases/${result.caseId}`);
    close();
  };

  return (
    <Dialog.Root open={open} onOpenChange={(o) => (o ? null : close())}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50" />
        <Dialog.Content
          data-testid="import-dialog"
          className={
            'fixed top-1/2 left-1/2 w-full max-w-md -translate-x-1/2 ' +
            'bg-card -translate-y-1/2 rounded-lg p-6 shadow-lg'
          }
        >
          <Dialog.Title className="text-foreground text-lg font-semibold">
            Import a portable bundle
          </Dialog.Title>
          <Dialog.Description className="text-muted-foreground mt-1 text-sm">
            Import a case exported from another Loom install. Its evidence is
            hash-verified and its signature checked; the source custody trail is
            preserved. Imported cases start closed.
          </Dialog.Description>

          <input
            ref={inputRef}
            type="file"
            accept=".zip"
            data-testid="import-file-input"
            className="mt-4 block w-full text-sm"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />

          {importing && (
            <progress
              data-testid="import-progress"
              className="mt-3 w-full"
              max={100}
              value={progress}
            />
          )}
          {error && (
            <p
              role="alert"
              className="mt-3 text-sm text-red-600 dark:text-red-400"
            >
              {error}
            </p>
          )}

          <div className="mt-6 flex justify-end gap-2">
            <button
              type="button"
              onClick={close}
              disabled={importing}
              className="text-muted-foreground rounded px-3 py-2 text-sm"
            >
              Cancel
            </button>
            <button
              type="button"
              data-testid="import-submit"
              onClick={handleImport}
              disabled={!file || importing}
              className={
                'bg-primary rounded px-4 py-2 text-sm font-medium ' +
                'text-primary-foreground hover:bg-primary/90 ' +
                'disabled:opacity-50'
              }
            >
              {importing ? 'Importing…' : 'Import'}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
