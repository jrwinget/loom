import { useState } from 'react';
import { useAuthStore } from '@/stores/auth-store';
import { apiClient } from '@/lib/api-client';
import type { User } from '@/types';

interface MfaChallengeTokens {
  access_token: string;
  refresh_token: string;
}

export function MfaChallenge(): React.ReactElement {
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const { mfaChallengeToken, setAuth, clearMfaChallenge } =
    useAuthStore();

  const handleSubmit = async (
    e: React.FormEvent,
  ): Promise<void> => {
    e.preventDefault();
    setError('');
    setSubmitting(true);

    try {
      const tokens =
        await apiClient.post<MfaChallengeTokens>(
          '/auth/mfa/challenge',
          {
            challenge_token: mfaChallengeToken,
            code,
          },
        );

      // fetch user profile with the new token
      useAuthStore.setState({ token: tokens.access_token });
      const user = await apiClient.get<User>('/auth/me');
      setAuth(tokens.access_token, user);
    } catch {
      setError('Invalid code. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="w-full max-w-sm space-y-6 rounded-lg border border-border bg-card p-8">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-foreground">
            Two-Factor Authentication
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Enter your authenticator code or a recovery
            code
          </p>
        </div>
        <form
          onSubmit={handleSubmit}
          className="space-y-4"
        >
          <div>
            <label
              htmlFor="mfa-code"
              className="block text-sm font-medium text-foreground"
            >
              Code
            </label>
            <input
              id="mfa-code"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              className="mt-1 block w-full rounded-md border border-input bg-background px-3 py-2 text-foreground"
              placeholder="000000"
              required
            />
          </div>
          {error && (
            <p
              role="alert"
              className="text-sm text-destructive"
            >
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={submitting || !code}
            className="w-full rounded-md bg-primary px-4 py-2 text-primary-foreground disabled:opacity-50"
          >
            {submitting ? 'Verifying...' : 'Verify'}
          </button>
          <button
            type="button"
            onClick={clearMfaChallenge}
            className="w-full text-sm text-muted-foreground hover:text-foreground"
          >
            Back to login
          </button>
        </form>
      </div>
    </div>
  );
}
