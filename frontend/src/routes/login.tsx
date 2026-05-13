import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { FactoryResetDialog } from '@/components/auth/FactoryResetDialog';
import { MfaChallenge } from '@/components/auth/MfaChallenge';
import { useFirstRunStatus } from '@/hooks/use-first-run';
import { apiClient } from '@/lib/api-client';
import { isTauri } from '@/lib/tauri-bridge';
import { useAuthStore } from '@/stores/auth-store';
import type { User } from '@/types';

interface LoginResponse {
  access_token?: string;
  refresh_token?: string;
  requires_mfa?: boolean;
  challenge_token?: string;
}

export function LoginPage(): React.ReactElement {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const { setAuth, setMfaChallenge, requiresMfa } = useAuthStore();
  const navigate = useNavigate();
  const { data: firstRun } = useFirstRunStatus();

  // recovery affordances are lite-only: server-profile installs have
  // admin reset paths instead. the factory-reset button additionally
  // requires the tauri bridge — the deletion runs in the desktop
  // shell, not the backend.
  const isLite = firstRun?.deployment_profile === 'lite';
  const showRecoveryLink = isLite;
  const showFactoryReset = isLite && isTauri;

  // fresh deploy with no users: send the operator through onboarding.
  useEffect(() => {
    if (firstRun?.first_run_required) {
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

      if (resp.requires_mfa && resp.challenge_token) {
        setMfaChallenge(resp.challenge_token);
        return;
      }

      if (resp.access_token) {
        useAuthStore.setState({
          token: resp.access_token,
        });
        const user = await apiClient.get<User>('/auth/me');
        setAuth(resp.access_token, user);
        navigate('/');
      }
    } catch {
      setError('Invalid email or password.');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="bg-card w-full max-w-sm space-y-6 rounded-lg border border-border p-8">
        <div className="text-center">
          <h1 className="text-2xl font-bold text-foreground">
            Sign in to Loom
          </h1>
        </div>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label
              htmlFor="email"
              className="block text-sm font-medium text-foreground"
            >
              Email
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 block w-full rounded-md border border-input bg-background px-3 py-2 text-foreground"
              required
            />
          </div>
          <div>
            <label
              htmlFor="password"
              className="block text-sm font-medium text-foreground"
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 block w-full rounded-md border border-input bg-background px-3 py-2 text-foreground"
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
            disabled={submitting}
            className="w-full rounded-md bg-primary px-4 py-2 text-primary-foreground disabled:opacity-50"
          >
            {submitting ? 'Signing in...' : 'Sign in'}
          </button>
        </form>

        {(showRecoveryLink || showFactoryReset) && (
          <div className="space-y-2 border-t border-border pt-4 text-center text-sm">
            {showRecoveryLink && (
              <Link
                to="/forgot-password"
                className="block text-muted-foreground hover:underline"
                data-testid="forgot-password-link"
              >
                Forgot your password?
              </Link>
            )}
            {showFactoryReset && (
              <button
                type="button"
                onClick={() => setResetOpen(true)}
                className="text-xs text-destructive hover:underline"
                data-testid="factory-reset-link"
              >
                Reset Loom (deletes all data)
              </button>
            )}
          </div>
        )}
      </div>
      {showFactoryReset && (
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
