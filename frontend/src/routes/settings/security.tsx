import { useState } from 'react';
import { ApiClientError, apiClient } from '@/lib/api-client';

interface SetupResponse {
  provisioningUri: string;
}

interface VerifyResponse {
  recoveryCodes: string[];
}

// surface the backend's detail rather than a fixed string; a bare
// catch here masked real failures the same way the old login page did.
function requestErrorMessage(err: unknown, fallback: string): string {
  if (err instanceof ApiClientError) {
    return err.detail || fallback;
  }
  return "Couldn't reach Loom. Make sure the app is running and try again.";
}

export function SecuritySettingsPage(): React.ReactElement {
  const [step, setStep] = useState<'idle' | 'setup' | 'verify' | 'done'>(
    'idle',
  );
  const [uri, setUri] = useState('');
  const [code, setCode] = useState('');
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [error, setError] = useState('');

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
      const resp = await apiClient.post<VerifyResponse>('/auth/mfa/verify', {
        code,
      });
      setRecoveryCodes(resp.recoveryCodes);
      setStep('done');
    } catch (err) {
      setError(requestErrorMessage(err, 'Invalid code. Please try again.'));
    }
  };

  if (step === 'done') {
    return (
      <div className="space-y-4">
        <h2 className="text-foreground text-xl font-bold">MFA Enabled</h2>
        <p className="text-muted-foreground text-sm">
          Save these recovery codes in a secure location. Each can be used once.
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
