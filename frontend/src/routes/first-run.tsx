import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiClient } from '@/lib/api-client';
import {
  useCompleteFirstRun,
  useFirstRunStatus,
} from '@/hooks/use-first-run';
import { useAuthStore } from '@/stores/auth-store';
import type { User } from '@/types';

const MIN_PASSWORD_LENGTH = 12;

export function FirstRunPage(): React.ReactElement {
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);

  const { data: status, isLoading, isError } = useFirstRunStatus();
  const complete = useCompleteFirstRun();

  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');

  // already-onboarded installs should not see this page.
  useEffect(() => {
    if (status && !status.first_run_required) {
      navigate('/', { replace: true });
    }
  }, [status, navigate]);

  const handleSubmit = async (
    e: React.FormEvent,
  ): Promise<void> => {
    e.preventDefault();
    setError('');

    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(
        `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`,
      );
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }

    try {
      const resp = await complete.mutateAsync({
        admin_email: email,
        admin_password: password,
        admin_full_name: fullName,
      });
      // stash the token so /auth/me can identify the new admin.
      useAuthStore.setState({ token: resp.access_token });
      const user = await apiClient.get<User>('/auth/me');
      setAuth(resp.access_token, user);
      navigate('/', { replace: true });
    } catch (err) {
      if (err instanceof Error) {
        const msg = err.message.toLowerCase();
        if (msg.includes('already completed')) {
          setError(
            'This install is already set up. Redirecting to sign in.',
          );
          setTimeout(() => navigate('/login'), 1500);
          return;
        }
        setError(err.message);
        return;
      }
      setError('Something went wrong. Please try again.');
    }
  };

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">Loading…</p>
      </div>
    );
  }

  if (isError || !status) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p role="alert" className="text-destructive">
          Unable to reach the backend. Is it running?
        </p>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-12">
      <div className="bg-card w-full max-w-lg space-y-6 rounded-lg border border-border p-8">
        <header className="space-y-2 text-center">
          <h1 className="text-2xl font-bold text-foreground">
            Welcome to Loom
          </h1>
          <p className="text-sm text-muted-foreground">
            Loom combines source documents into defensible event timelines.
            Let&apos;s set up your admin account.
          </p>
        </header>

        {status.deployment_profile === 'lite' && status.data_dir && (
          <div className="rounded-md border border-border bg-muted/40 p-3 text-sm">
            <p className="text-muted-foreground">Data directory</p>
            <p className="break-all font-mono text-foreground">
              {status.data_dir}
            </p>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
          <div>
            <label
              htmlFor="fullName"
              className="block text-sm font-medium text-foreground"
            >
              Full name
            </label>
            <input
              id="fullName"
              type="text"
              autoComplete="name"
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="mt-1 block w-full rounded-md border border-input bg-background px-3 py-2 text-foreground"
              required
              minLength={1}
            />
          </div>
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
              Password (minimum {MIN_PASSWORD_LENGTH} characters)
            </label>
            <input
              id="password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 block w-full rounded-md border border-input bg-background px-3 py-2 text-foreground"
              required
              minLength={MIN_PASSWORD_LENGTH}
            />
          </div>
          <div>
            <label
              htmlFor="confirm"
              className="block text-sm font-medium text-foreground"
            >
              Confirm password
            </label>
            <input
              id="confirm"
              type="password"
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
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
            disabled={complete.isPending}
            className="w-full rounded-md bg-primary px-4 py-2 text-primary-foreground disabled:opacity-50"
          >
            {complete.isPending ? 'Creating account…' : 'Create admin account'}
          </button>
        </form>
      </div>
    </div>
  );
}
