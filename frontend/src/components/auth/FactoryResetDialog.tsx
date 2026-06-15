// destructive reset affordance for desktop-lite operators who have
// lost their password and have no working recovery code. shows a
// typed-confirmation gate (operator must type the word RESET) and a
// plain-language list of what gets deleted, then invokes the
// ``factory_reset`` tauri command. on success the sidecar restarts
// into a fresh first-run state and the operator is redirected to
// /first-run.

import { useEffect, useRef, useState } from 'react';
import { factoryReset } from '@/lib/tauri-bridge';

interface FactoryResetDialogProps {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const CONFIRM_WORD = 'RESET';

export function FactoryResetDialog({
  open,
  onClose,
  onSuccess,
}: FactoryResetDialogProps): React.ReactElement | null {
  const [confirmation, setConfirmation] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [wasOpen, setWasOpen] = useState(open);
  const inputRef = useRef<HTMLInputElement>(null);

  // clear the gate during render on each open transition so a reopened
  // dialog never shows a stale confirmation or error.
  if (open && !wasOpen) {
    setWasOpen(true);
    setConfirmation('');
    setError('');
    setSubmitting(false);
  } else if (!open && wasOpen) {
    setWasOpen(false);
  }

  useEffect(() => {
    if (!open) return undefined;
    // give the dialog a tick to mount before focusing.
    const id = window.setTimeout(() => inputRef.current?.focus(), 0);
    return () => window.clearTimeout(id);
  }, [open]);

  // close on Escape so keyboard users aren't trapped.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape' && !submitting) onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, submitting, onClose]);

  if (!open) return null;

  const isArmed = confirmation === CONFIRM_WORD && !submitting;

  async function handleConfirm(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    if (!isArmed) return;
    setSubmitting(true);
    setError('');
    try {
      await factoryReset();
      onSuccess();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Failed to reset. The desktop shell may be unavailable.',
      );
      setSubmitting(false);
    }
  }

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="factory-reset-title"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
      data-testid="factory-reset-dialog"
    >
      <div className="bg-card w-full max-w-md space-y-4 rounded-lg border border-border p-6">
        <h2
          id="factory-reset-title"
          className="text-lg font-semibold text-destructive"
        >
          Reset this Loom install?
        </h2>
        <p className="text-sm text-muted-foreground">
          This is permanent. You should only do this if you cannot sign in and
          have no valid recovery code.
        </p>
        <div className="rounded-md border border-border bg-muted/40 p-3 text-sm">
          <p className="font-medium text-foreground">What gets deleted:</p>
          <ul className="ml-4 mt-2 list-disc space-y-1 text-muted-foreground">
            <li>The local database (every case, asset, and audit row)</li>
            <li>Uploaded originals and derived files</li>
            <li>Your chosen data-directory preference</li>
          </ul>
          <p className="mt-2 text-xs text-muted-foreground">
            Bootstrap secrets are preserved so the install identity stays
            stable.
          </p>
        </div>
        <form onSubmit={handleConfirm} className="space-y-3" noValidate>
          <label
            htmlFor="factory-reset-confirm"
            className="block text-sm font-medium text-foreground"
          >
            Type <span className="font-mono font-bold">{CONFIRM_WORD}</span> to
            continue
          </label>
          <input
            id="factory-reset-confirm"
            ref={inputRef}
            type="text"
            autoComplete="off"
            spellCheck={false}
            value={confirmation}
            onChange={(e) => setConfirmation(e.target.value)}
            disabled={submitting}
            className="block w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-foreground"
          />
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={submitting}
              className="rounded-md border border-border bg-background px-4 py-2 text-sm text-foreground hover:bg-accent disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!isArmed}
              className="rounded-md bg-destructive px-4 py-2 text-sm text-destructive-foreground hover:bg-destructive/90 disabled:opacity-50"
            >
              {submitting ? 'Resetting…' : 'Reset Loom'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
