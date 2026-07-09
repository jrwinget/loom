import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { FactoryResetDialog } from '@/components/auth/FactoryResetDialog';
import { MfaChallenge } from '@/components/auth/MfaChallenge';
import { useFirstRunStatus } from '@/hooks/use-first-run';
import { ApiClientError, apiClient } from '@/lib/api-client';
import { isTauri } from '@/lib/tauri-bridge';
import { useAuthStore } from '@/stores/auth-store';
import type { User } from '@/types';

interface LoginResponse {
  accessToken?: string;
  refreshToken?: string;
  requiresMfa?: boolean;
  challengeToken?: string;
}

// the api-client throws ApiClientError only after a response arrives, so
// the status is meaningful; a thrown TypeError means the request never
// reached the sidecar. collapsing every failure into "invalid email or
// password" (the old behavior) is what made this flow undiagnosable.
function loginErrorMessage(err: unknown): string {
  if (err instanceof ApiClientError) {
    if (err.status === 401) {
      return 'Invalid email or password.';
    }
    if (err.status === 429) {
      return 'Too many attempts. Wait a minute and try again.';
    }
    return err.detail || 'Sign-in failed. Please try again.';
  }
  return "Couldn't reach Loom. Make sure the app is running and try again.";
}

export function LoginPage(): React.ReactElement {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const { setAuth, setMfaChallenge, requiresMfa } = useAuthStore();
  const navigate = useNavigate();
  const {
    data: firstRun,
    isLoading: firstRunLoading,
    isError: firstRunError,
  } = useFirstRunStatus();

  // recovery affordances are lite-only: server-profile installs have
  // admin reset paths instead. the factory-reset button additionally
  // requires the tauri bridge — the deletion runs in the desktop
  // shell, not the backend.
  const isLite = firstRun?.deploymentProfile === 'lite';
  const showRecoveryLink = isLite;
  // even when the status query is errored we still want Reset Loom
  // available inside the desktop shell: the operator's only escape
  // hatch from a wedged install must not depend on a backend that
  // already isn't answering.
  const canFactoryReset = isTauri && (isLite || firstRunError);

  // fresh deploy with no users: send the operator through onboarding.
  useEffect(() => {
    if (firstRun?.firstRunRequired) {
      navigate('/first-run', { replace: true });
    }
  }, [firstRun, navigate]);

  if (requiresMfa()) {
    return <MfaChallenge />;
  }

  const handleSubmit = async (e: React.FormEvent): Promise<void> => {
    e.preventDefault();
    setError('');
    setSubmitting(true);

    try {
      const resp = await apiClient.post<LoginResponse>('/auth/login', {
        email,
        password,
      });

      if (resp.requiresMfa && resp.challengeToken) {
        setMfaChallenge(resp.challengeToken);
        return;
      }

      if (resp.accessToken) {
        const accessToken = resp.accessToken;
        // set the token so the /auth/me request is authenticated, then
        // load the profile. a failure here is NOT a credentials problem,
        // so surface it distinctly and don't leave a half-auth token.
        useAuthStore.setState({ token: accessToken });
        try {
          const user = await apiClient.get<User>('/auth/me');
          setAuth(accessToken, user);
          navigate('/');
        } catch {
          useAuthStore.getState().clearAuth();
          setError('Signed in, but could not load your profile. Try again.');
        }
      }
    } catch (err) {
      setError(loginErrorMessage(err));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="border-border bg-card w-full max-w-sm space-y-6 rounded-lg border p-8">
        <div className="text-center">
          <h1 className="text-foreground text-2xl font-bold">
            Sign in to Loom
          </h1>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="email"
              className="text-foreground block text-sm font-medium"
            >
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="border-input bg-background text-foreground mt-1 block w-full rounded-md border px-3 py-2"
              required
            />
          </div>
          <div>
            <label
              htmlFor="password"
              className="text-foreground block text-sm font-medium"
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="border-input bg-background text-foreground mt-1 block w-full rounded-md border px-3 py-2"
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
            disabled={submitting}
            className="bg-primary text-primary-foreground w-full rounded-md px-4 py-2 disabled:opacity-50"
          >
            {submitting ? 'Signing in...' : 'Sign in'}
          </button>
        </form>

        <div className="border-border space-y-2 border-t pt-4 text-center text-sm">
          {firstRunLoading && (
            <p className="text-muted-foreground" data-testid="recovery-loading">
              Loading recovery options…
            </p>
          )}
          {firstRunError && (
            <p
              role="alert"
              className="text-destructive"
              data-testid="recovery-error"
            >
              Couldn't reach the backend. If recovery options are missing,
              restart Loom.
            </p>
          )}
          {!firstRunLoading && !firstRunError && showRecoveryLink && (
            <Link
              to="/forgot-password"
              className="text-muted-foreground block hover:underline"
              data-testid="forgot-password-link"
            >
              Forgot your password?
            </Link>
          )}
          {canFactoryReset && (
            <button
              type="button"
              onClick={() => setResetOpen(true)}
              className="text-destructive text-xs hover:underline"
              data-testid="factory-reset-link"
            >
              Reset Loom (deletes all data)
            </button>
          )}
        </div>
      </div>
      {canFactoryReset && (
        <FactoryResetDialog
          open={resetOpen}
          onClose={() => setResetOpen(false)}
          onSuccess={() => {
            setResetOpen(false);
            // sidecar respawns into a fresh first-run state; route
            // there so the operator picks up onboarding.
            navigate('/first-run', { replace: true });
          }}
        />
      )}
    </div>
  );
}
