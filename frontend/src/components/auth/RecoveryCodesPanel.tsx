// renders the operator's single-use password recovery codes exactly
// once. the parent (FirstRunPage) supplies the plaintext codes
// returned from /first-run/complete; this component owns the
// "i've saved these" confirmation gate.
//
// rationale: the backend retains only sha256 hashes, so the plaintext
// only exists in memory during this render. unmounting the page
// without confirming means the codes are gone — the operator can
// still factory-reset and re-bootstrap, so this isn't catastrophic,
// but the UI should make the consequences explicit.

import { useState } from 'react';

interface RecoveryCodesPanelProps {
  codes: string[];
  onAcknowledge: () => void;
}

export function RecoveryCodesPanel({
  codes,
  onAcknowledge,
}: RecoveryCodesPanelProps): React.ReactElement {
  const [confirmed, setConfirmed] = useState(false);
  const [copyState, setCopyState] = useState<'idle' | 'copied' | 'error'>(
    'idle',
  );

  async function handleCopy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(codes.join('\n'));
      setCopyState('copied');
      window.setTimeout(() => setCopyState('idle'), 2000);
    } catch {
      setCopyState('error');
    }
  }

  function handleDownload(): void {
    const blob = new Blob(
      [
        '# Loom recovery codes\n',
        '# Single-use. Each code can recover your account exactly once.\n',
        '# Keep this file somewhere safe — Loom cannot show these again.\n\n',
        codes.join('\n'),
        '\n',
      ],
      { type: 'text/plain' },
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'loom-recovery-codes.txt';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  return (
    <section
      aria-labelledby="recovery-codes-heading"
      className="space-y-4"
      data-testid="recovery-codes-panel"
    >
      <header className="space-y-2">
        <h2
          id="recovery-codes-heading"
          className="text-lg font-semibold text-foreground"
        >
          Save your recovery codes
        </h2>
        <p className="text-sm text-muted-foreground">
          Loom cannot reset your password for you — there is no email server and
          no second admin. These eight single-use codes are the only way to
          recover your account without losing your data. Store them in a
          password manager or print them.
        </p>
      </header>

      <ul
        data-testid="recovery-codes-list"
        className="grid grid-cols-1 gap-2 rounded-md border border-border bg-muted/40 p-4 font-mono text-sm sm:grid-cols-2"
      >
        {codes.map((code) => (
          <li
            key={code}
            className="select-all break-all text-foreground"
            data-testid="recovery-code"
          >
            {code}
          </li>
        ))}
      </ul>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={handleCopy}
          className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground hover:bg-accent"
        >
          {copyState === 'copied' ? 'Copied!' : 'Copy to clipboard'}
        </button>
        <button
          type="button"
          onClick={handleDownload}
          className="rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground hover:bg-accent"
        >
          Download as .txt
        </button>
        {copyState === 'error' && (
          <p role="alert" className="w-full text-xs text-destructive">
            Could not access the clipboard. Use the download button instead.
          </p>
        )}
      </div>

      <label className="flex items-start gap-2 text-sm text-foreground">
        <input
          type="checkbox"
          checked={confirmed}
          onChange={(e) => setConfirmed(e.target.checked)}
          className="mt-1"
          data-testid="recovery-codes-ack"
        />
        <span>
          I have stored these codes somewhere safe. I understand Loom will not
          show them again.
        </span>
      </label>

      <button
        type="button"
        onClick={onAcknowledge}
        disabled={!confirmed}
        className="w-full rounded-md bg-primary px-4 py-2 text-primary-foreground disabled:opacity-50"
      >
        Continue to Loom
      </button>
    </section>
  );
}
