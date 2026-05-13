// password recovery using a single-use code minted at first-run. the
// operator enters their email, one of their stored codes, and a new
// password. on success they're routed to /login to sign in normally;
// no token is issued here so any active mfa enrollment still applies.
//
// the page is intentionally available on every profile — the backend
// endpoint is too — but the link into it is only rendered on lite
// (see LoginPage). on server-profile deploys the admin reset path
// supersedes this flow.

import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { apiClient } from '@/lib/api-client';

const MIN_PASSWORD_LENGTH = 12;

interface RecoverResponse {
  codes_remaining: number;
}

export function ForgotPasswordPage(): React.ReactElement {
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [remaining, setRemaining] = useState<number | null>(null);

  async function handleSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    setError('');

    if (password.length < MIN_PASSWORD_LENGTH) {
      setError(`Password must be at least ${MIN_PASSWORD_LENGTH} characters.`);
      return;
    }
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }

    setSubmitting(true);
    try {
      const resp = await apiClient.post<RecoverResponse>(
        '/auth/recover-password',
        {
          email,
          recovery_code: code.trim(),
          new_password: password,
        },
      );
      setRemaining(resp.codes_remaining);
      // redirect after a short pause so the operator sees the
      // "codes remaining" hint before the page changes.
      window.setTimeout(() => navigate('/login', { replace: true }), 2500);
    } catch (err) {
      // backend returns the same detail for unknown-email and
      // wrong-code on purpose; surface it verbatim so the operator
      // sees the same message regardless of which mistake they made.
      setError(
        err instanceof Error
          ? err.message
          : 'Could not reset your password. Try again.',
      );
      setSubmitting(false);
    }
  }

  if (remaining !== null) {
    return (
      <div className="flex min-h-screen items-center justify-center px-4">
        <div
          className="bg-card w-full max-w-sm space-y-4 rounded-lg border border-border p-8 text-center"
          data-testid="forgot-password-success"
        >
          <h1 className="text-xl font-semibold text-foreground">
            Password reset
          </h1>
          <p className="text-sm text-muted-foreground">
            You can now sign in with your new password.
          </p>
          <p className="text-xs text-muted-foreground">
            {remaining === 0
              ? 'You have no recovery codes left. Generate a new set after signing in.'
              : `${remaining} recovery code${remaining === 1 ? '' : 's'} remaining.`}
          </p>
          <p className="text-xs text-muted-foreground">Redirecting…</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-12">
      <div className="bg-card w-full max-w-sm space-y-6 rounded-lg border border-border p-8">
        <header className="text-center">
          <h1 className="text-2xl font-bold text-foreground">
            Recover your password
          </h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Enter one of the single-use codes you saved when you first set up
            Loom.
          </p>
        </header>

        <form onSubmit={handleSubmit} className="space-y-4" noValidate>
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
              htmlFor="code"
              className="block text-sm font-medium text-foreground"
            >
              Recovery code
            </label>
            <input
              id="code"
              type="text"
              autoComplete="one-time-code"
              spellCheck={false}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="aaaaa-bbbbb-ccccc-ddddd"
              className="mt-1 block w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-foreground"
              required
              minLength={20}
            />
          </div>
          <div>
            <label
              htmlFor="new-password"
              className="block text-sm font-medium text-foreground"
            >
              New password (minimum {MIN_PASSWORD_LENGTH} characters)
            </label>
            <input
              id="new-password"
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
              htmlFor="confirm-password"
              className="block text-sm font-medium text-foreground"
            >
              Confirm new password
            </label>
            <input
              id="confirm-password"
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
            disabled={submitting}
            className="w-full rounded-md bg-primary px-4 py-2 text-primary-foreground disabled:opacity-50"
          >
            {submitting ? 'Resetting…' : 'Reset password'}
          </button>
        </form>

        <p className="text-center text-sm">
          <Link to="/login" className="text-muted-foreground hover:underline">
            Back to sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
