import { useState } from 'react';
import { apiClient } from '@/lib/api-client';

interface SetupResponse {
  provisioning_uri: string;
}

interface VerifyResponse {
  recovery_codes: string[];
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
      setUri(resp.provisioning_uri);
      setStep('setup');
    } catch {
      setError('Failed to start MFA setup.');
    }
  };

  const handleVerify = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    setError('');
    try {
      const resp = await apiClient.post<VerifyResponse>('/auth/mfa/verify', {
        code,
      });
      setRecoveryCodes(resp.recovery_codes);
      setStep('done');
    } catch {
      setError('Invalid code. Please try again.');
    }
  };

  if (step === 'done') {
    return (
      <div className="space-y-4">
        <h2 className="text-xl font-bold text-foreground">MFA Enabled</h2>
        <p className="text-sm text-muted-foreground">
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
        <h2 className="text-xl font-bold text-foreground">
          Setup Authenticator
        </h2>
        <p className="break-all text-sm text-muted-foreground">
          Add this URI to your authenticator app: <code>{uri}</code>
        </p>
        <form onSubmit={handleVerify} className="space-y-4">
          <input
            type="text"
            inputMode="numeric"
            value={code}
            onChange={(e) => setCode(e.target.value)}
            placeholder="Enter code from app"
            className="block w-full rounded-md border border-input bg-background px-3 py-2 text-foreground"
            required
          />
          {error && <p className="text-sm text-destructive">{error}</p>}
          <button
            type="submit"
            className="rounded-md bg-primary px-4 py-2 text-primary-foreground"
          >
            Verify
          </button>
        </form>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold text-foreground">Security Settings</h2>
      <p className="text-sm text-muted-foreground">
        Protect your account with two-factor authentication.
      </p>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <button
        onClick={handleSetup}
        className="rounded-md bg-primary px-4 py-2 text-primary-foreground"
      >
        Enable MFA
      </button>
    </div>
  );
}
