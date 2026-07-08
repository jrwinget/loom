import { useState } from 'react';
import { useAuthStore } from '@/stores/auth-store';
import { ApiClientError, apiClient } from '@/lib/api-client';
import type { User } from '@/types';

interface MfaChallengeTokens {
  accessToken: string;
  refreshToken: string;
}

// same rationale as the login page: collapsing every failure into
// "invalid code" hides rate limits, expired challenges, and transport
// errors, which is the masking pattern that made login undiagnosable.
function challengeErrorMessage(err: unknown): string {
  if (err instanceof ApiClientError) {
    if (err.status === 429) {
      return 'Too many attempts. Wait a minute and try again.';
    }
    return err.detail || 'Invalid code. Please try again.';
  }
  return "Couldn't reach Loom. Make sure the app is running and try again.";
}

export function MfaChallenge(): React.ReactElement {
  const [code, setCode] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const { mfaChallengeToken, setAuth, clearMfaChallenge } = useAuthStore();

  const handleSubmit = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    setError('');
    setSubmitting(true);

    try {
      const tokens = await apiClient.post<MfaChallengeTokens>(
        '/auth/mfa/challenge',
        {
          challenge_token: mfaChallengeToken,
          code,
        },
      );

      // set the token so /auth/me is authenticated. a failure there is
      // not a code problem, so surface it distinctly and don't leave a
      // half-auth token behind.
      useAuthStore.setState({ token: tokens.accessToken });
      try {
        const user = await apiClient.get<User>('/auth/me');
        setAuth(tokens.accessToken, user);
      } catch {
        useAuthStore.getState().clearAuth();
        setError('Verified, but could not load your profile. Try again.');
      }
    } catch (err) {
      setError(challengeErrorMessage(err));
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
            Enter your authenticator code or a recovery code
          </p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
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
            <p role="alert" className="text-sm text-destructive">
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
