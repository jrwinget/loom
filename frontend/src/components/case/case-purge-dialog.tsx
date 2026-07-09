// irreversible destroy affordance for a case. gates behind a typed
// confirmation of the exact case title plus a required reason, then
// calls DELETE /cases/{id}. the backend writes an append-only audit
// tombstone (title, reason, asset ids + hashes) before deleting
// anything, so the chain of custody survives the destruction. on
// success the parent navigates away.

import { useEffect, useRef, useState } from 'react';
import { usePurgeCase } from '@/hooks/use-case';

interface CasePurgeDialogProps {
  open: boolean;
  onClose: () => void;
  onPurged: () => void;
  caseId: string;
  caseTitle: string;
  assetCount: number;
}

export function CasePurgeDialog({
  open,
  onClose,
  onPurged,
  caseId,
  caseTitle,
  assetCount,
}: CasePurgeDialogProps): React.ReactElement | null {
  const [confirmation, setConfirmation] = useState('');
  const [reason, setReason] = useState('');
  const [error, setError] = useState('');
  const [wasOpen, setWasOpen] = useState(open);
  const inputRef = useRef<HTMLInputElement>(null);
  const purge = usePurgeCase();

  // clear the gate during render on each open transition so a reopened
  // dialog never shows a stale confirmation, reason, or error.
  if (open && !wasOpen) {
    setWasOpen(true);
    setConfirmation('');
    setReason('');
    setError('');
  } else if (!open && wasOpen) {
    setWasOpen(false);
  }

  useEffect(() => {
    if (!open) return undefined;
    const id = window.setTimeout(() => inputRef.current?.focus(), 0);
    return () => window.clearTimeout(id);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape' && !purge.isPending) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, purge.isPending, onClose]);

  if (!open) return null;

  const titleMatches = confirmation === caseTitle;
  const reasonGiven = reason.trim().length > 0;
  const isArmed = titleMatches && reasonGiven && !purge.isPending;

  async function handleConfirm(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    if (!isArmed) return;
    setError('');
    try {
      await purge.mutateAsync({ id: caseId, confirmTitle: caseTitle, reason });
      onPurged();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to destroy the case. Please try again.',
      );
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="case-purge-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
      data-testid="case-purge-dialog"
    >
      <div className="border-border bg-card w-full max-w-md space-y-4 rounded-lg border p-6">
        <h2
          id="case-purge-title"
          className="text-destructive text-lg font-semibold"
        >
          Destroy this case?
        </h2>
        <p className="text-muted-foreground text-sm">
          This permanently destroys the case and cannot be undone.
        </p>
        <div className="border-border bg-muted/40 rounded-md border p-3 text-sm">
          <p className="text-foreground font-medium">What gets destroyed:</p>
          <ul className="text-muted-foreground mt-2 ml-4 list-disc space-y-1">
            <li>
              {assetCount} {assetCount === 1 ? 'asset' : 'assets'} and their
              original files
            </li>
            <li>The timeline and every annotation</li>
          </ul>
          <p className="text-muted-foreground mt-2 text-xs">
            An audit tombstone recording what was destroyed (title, reason, and
            each asset&apos;s hash) is preserved.
          </p>
        </div>
        <form onSubmit={handleConfirm} className="space-y-3" noValidate>
          <label
            htmlFor="case-purge-confirm"
            className="text-foreground block text-sm font-medium"
          >
            Type the case title{' '}
            <span className="font-mono font-bold">{caseTitle}</span> to confirm
          </label>
          <input
            id="case-purge-confirm"
            ref={inputRef}
            type="text"
            autoComplete="off"
            spellCheck={false}
            value={confirmation}
            onChange={(e) => setConfirmation(e.target.value)}
            disabled={purge.isPending}
            className="border-input bg-background text-foreground block w-full rounded-md border px-3 py-2 font-mono"
          />
          <label
            htmlFor="case-purge-reason"
            className="text-foreground block text-sm font-medium"
          >
            Reason
          </label>
          <textarea
            id="case-purge-reason"
            rows={3}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            disabled={purge.isPending}
            className="border-input bg-background text-foreground block w-full rounded-md border px-3 py-2 text-sm"
          />
          {error && (
            <p role="alert" className="text-destructive text-sm">
              {error}
            </p>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={purge.isPending}
              className="border-border bg-background text-foreground hover:bg-accent rounded-md border px-4 py-2 text-sm disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!isArmed}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90 rounded-md px-4 py-2 text-sm disabled:opacity-50"
            >
              {purge.isPending ? 'Destroying…' : 'Destroy case'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
