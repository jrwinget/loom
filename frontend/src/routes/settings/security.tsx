import { useState } from 'react';
import { ApiClientError, apiClient } from '@/lib/api-client';
import { RecoveryCodesPanel } from '@/components/auth/RecoveryCodesPanel';
import { useAuthStore } from '@/stores/auth-store';

interface SetupResponse {
  provisioningUri: string;
}

interface CodesResponse {
  recoveryCodes: string[];
}

const NEW_CODES_DESCRIPTION =
  'These replace your previous recovery codes — the old codes no longer ' +
  'work. Each new code can be used once.';

// surface the backend's detail rather than a fixed string; a bare catch
// here masked real failures the same way the old login page did.
function requestErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiClientError) {
    return err.detail || fallback;
  }
  return "Couldn't reach Loom. Make sure the app is running and try again.";
}

function setStoreMfa(enabled: boolean): void {
  useAuthStore.setState((state) =>
    state.user ? { user: { ...state.user, mfaEnabled: enabled } } : {},
  );
}

export function SecuritySettingsPage(): React.ReactElement {
  const user = useAuthStore((state) => state.user);
  const [enrolled, setEnrolled] = useState(user?.mfaEnabled ?? false);

  // enrollment flow
  const [step, setStep] = useState<'idle' | 'setup' | 'done'>('idle');
  const [uri, setUri] = useState('');
  const [code, setCode] = useState('');
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [error, setError] = useState('');

  // recovery-code regeneration flow
  const [regenOpen, setRegenOpen] = useState(false);
  const [regenCode, setRegenCode] = useState('');
  const [newCodes, setNewCodes] = useState<string[]>([]);
  const [regenError, setRegenError] = useState('');

  // disable flow
  const [password, setPassword] = useState('');
  const [confirmDisable, setConfirmDisable] = useState(false);
  const [disableError, setDisableError] = useState('');

  const handleSetup = async (): Promise<void> => {
    setError('');
    try {
      const resp = await apiClient.post<SetupResponse>('/auth/mfa/setup');
      setUri(resp.provisioningUri);
      setStep('setup');
    } catch (err) {
      setError(requestErrorMessage(err, 'Failed to start MFA setup.'));
    }
  };

  const handleVerify = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    setError('');
    try {
      const resp = await apiClient.post<CodesResponse>('/auth/mfa/verify', {
        code,
      });
      setRecoveryCodes(resp.recoveryCodes);
      setStep('done');
      setStoreMfa(true);
    } catch (err) {
      setError(requestErrorMessage(err, 'Invalid code. Please try again.'));
    }
  };

  const handleRegenerate = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    setRegenError('');
    try {
      const resp = await apiClient.post<CodesResponse>(
        '/auth/mfa/recovery-codes',
        { code: regenCode },
      );
      setNewCodes(resp.recoveryCodes);
      setRegenOpen(false);
      setRegenCode('');
    } catch (err) {
      setRegenError(requestErrorMessage(err, 'Could not regenerate codes.'));
    }
  };

  const handleDisable = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    setDisableError('');
    try {
      await apiClient.delete<void>('/auth/mfa', { password });
      setEnrolled(false);
      setStoreMfa(false);
      setPassword('');
      setConfirmDisable(false);
    } catch (err) {
      setDisableError(
        requestErrorMessage(err, 'Could not disable two-factor.'),
      );
    }
  };

  // ----- enrollment views (shown until the account has mfa) -----
  if (!enrolled) {
    if (step === 'done') {
      return (
        <div className="space-y-4">
          <h2 className="text-foreground text-xl font-bold">MFA Enabled</h2>
          <p className="text-muted-foreground text-sm">
            Save these recovery codes in a secure location. Each can be used
            once.
          </p>
          <ul
            className="space-y-1 font-mono text-sm"
            data-testid="recovery-codes"
          >
            {recoveryCodes.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
        </div>
      );
    }

    if (step === 'setup') {
      return (
        <div className="space-y-4">
          <h2 className="text-foreground text-xl font-bold">
            Setup Authenticator
          </h2>
          <p className="text-muted-foreground text-sm break-all">
            Add this URI to your authenticator app: <code>{uri}</code>
          </p>
          <form onSubmit={handleVerify} className="space-y-4">
            <input
              type="text"
              inputMode="numeric"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="Enter code from app"
              className="border-input bg-background text-foreground block w-full rounded-md border px-3 py-2"
              required
            />
            {error && (
              <p role="alert" className="text-destructive text-sm">
                {error}
              </p>
            )}
            <button
              type="submit"
              className="bg-primary text-primary-foreground rounded-md px-4 py-2"
            >
              Verify
            </button>
          </form>
        </div>
      );
    }

    return (
      <div className="space-y-4">
        <h2 className="text-foreground text-xl font-bold">Security Settings</h2>
        <p className="text-muted-foreground text-sm">
          Protect your account with two-factor authentication.
        </p>
        {error && (
          <p role="alert" className="text-destructive text-sm">
            {error}
          </p>
        )}
        <button
          onClick={handleSetup}
          className="bg-primary text-primary-foreground rounded-md px-4 py-2"
        >
          Enable MFA
        </button>
      </div>
    );
  }

  // ----- enrolled views -----
  if (newCodes.length > 0) {
    return (
      <RecoveryCodesPanel
        codes={newCodes}
        title="Your new recovery codes"
        description={NEW_CODES_DESCRIPTION}
        acknowledgeLabel="Done"
        onAcknowledge={() => setNewCodes([])}
      />
    );
  }

  return (
    <div className="space-y-8">
      <div className="space-y-2">
        <h2 className="text-foreground text-xl font-bold">Security Settings</h2>
        <p className="text-muted-foreground text-sm">
          Two-factor authentication is on for your account.
        </p>
      </div>

      <section
        aria-labelledby="recovery-card-heading"
        className="border-border space-y-4 rounded-md border p-4"
      >
        <h3
          id="recovery-card-heading"
          className="text-foreground text-lg font-semibold"
        >
          Recovery codes
        </h3>
        <p className="text-muted-foreground text-sm">
          Regenerating issues a new set and invalidates your previous codes. You
          will need a code from your authenticator app to continue.
        </p>
        {!regenOpen ? (
          <button
            type="button"
            onClick={() => setRegenOpen(true)}
            className="bg-primary text-primary-foreground rounded-md px-4 py-2"
          >
            Regenerate codes
          </button>
        ) : (
          <form onSubmit={handleRegenerate} className="space-y-4">
            <input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={regenCode}
              onChange={(e) => setRegenCode(e.target.value)}
              placeholder="Enter code from app"
              aria-label="Authenticator code"
              className="border-input bg-background text-foreground block w-full rounded-md border px-3 py-2"
              required
            />
            {regenError && (
              <p role="alert" className="text-destructive text-sm">
                {regenError}
              </p>
            )}
            <div className="flex gap-2">
              <button
                type="submit"
                className="bg-primary text-primary-foreground rounded-md px-4 py-2"
              >
                Generate new codes
              </button>
              <button
                type="button"
                onClick={() => {
                  setRegenOpen(false);
                  setRegenCode('');
                  setRegenError('');
                }}
                className="border-border text-foreground rounded-md border px-4 py-2"
              >
                Cancel
              </button>
            </div>
          </form>
        )}
      </section>

      <section
        aria-labelledby="disable-card-heading"
        className="border-destructive/50 space-y-4 rounded-md border p-4"
      >
        <h3
          id="disable-card-heading"
          className="text-destructive text-lg font-semibold"
        >
          Disable two-factor authentication
        </h3>
        <p className="text-muted-foreground text-sm">
          This removes the second factor from your account. Confirm with your
          password — a signed-in session alone is not enough.
        </p>
        <form onSubmit={handleDisable} className="space-y-4">
          <input
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Account password"
            aria-label="Account password"
            className="border-input bg-background text-foreground block w-full rounded-md border px-3 py-2"
            required
          />
          <label className="text-foreground flex items-start gap-2 text-sm">
            <input
              type="checkbox"
              checked={confirmDisable}
              onChange={(e) => setConfirmDisable(e.target.checked)}
              className="mt-1"
              data-testid="disable-confirm"
            />
            <span>
              I understand this removes the second factor protecting my account.
            </span>
          </label>
          {disableError && (
            <p role="alert" className="text-destructive text-sm">
              {disableError}
            </p>
          )}
          <button
            type="submit"
            disabled={!password || !confirmDisable}
            className="bg-destructive text-destructive-foreground rounded-md px-4 py-2 disabled:opacity-50"
          >
            Disable two-factor authentication
          </button>
        </form>
      </section>
    </div>
  );
}
