import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
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
  const navigate = useNavigate();

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
        // setAuth clears the challenge, which alone would just swap
        // the login form back in under the now-authenticated user —
        // leave the page like the password-only path does
        navigate('/', { replace: true });
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
      <div className="border-border bg-card w-full max-w-sm space-y-6 rounded-lg border p-8">
        <div className="text-center">
          <h1 className="text-foreground text-2xl font-bold">
            Two-Factor Authentication
          </h1>
          <p className="text-muted-foreground mt-2 text-sm">
            Enter your authenticator code or a recovery code
          </p>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="mfa-code"
              className="text-foreground block text-sm font-medium"
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
              className="border-input bg-background text-foreground mt-1 block w-full rounded-md border px-3 py-2"
              placeholder="000000"
              required
            />
          </div>
          {error && (
            <p role="alert" className="text-destructive text-sm">
              {error}
            </p>
          )}
          <button
            type="submit"
            disabled={submitting || !code}
            className="bg-primary text-primary-foreground w-full rounded-md px-4 py-2 disabled:opacity-50"
          >
            {submitting ? 'Verifying...' : 'Verify'}
          </button>
          <button
            type="button"
            onClick={clearMfaChallenge}
            className="text-muted-foreground hover:text-foreground w-full text-sm"
          >
            Back to login
          </button>
        </form>
      </div>
    </div>
  );
}
