import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { RecoveryCodesPanel } from '@/components/auth/RecoveryCodesPanel';
import { apiClient } from '@/lib/api-client';
import {
  pickDirectory,
  persistDataDirectory,
  restartBackend,
} from '@/lib/tauri-bridge';
import { useCompleteFirstRun, useFirstRunStatus } from '@/hooks/use-first-run';
import { useStorageCheck } from '@/hooks/use-storage';
import { useAuthStore } from '@/stores/auth-store';
import type { User } from '@/types';

const MIN_PASSWORD_LENGTH = 12;

type Step = 'data_dir' | 'admin' | 'recovery_codes';

export function FirstRunPage(): React.ReactElement {
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);

  const { data: status, isLoading, isError } = useFirstRunStatus();
  const complete = useCompleteFirstRun();
  const check = useStorageCheck();

  // server-profile installs skip the data-dir step entirely.
  const isLite = status?.deployment_profile === 'lite';

  const [step, setStep] = useState<Step>('admin');
  const [chosenDir, setChosenDir] = useState<string | null>(null);
  const [dirError, setDirError] = useState('');
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);

  // pick the initial step once the status payload arrives.
  useEffect(() => {
    if (status && status.first_run_required) {
      setStep(isLite ? 'data_dir' : 'admin');
      if (isLite && !chosenDir) {
        setChosenDir(status.data_dir ?? null);
      }
    }
  }, [status, isLite, chosenDir]);

  // already-onboarded installs should not see this page. exempt the
  // recovery_codes step: by the time we're there we've already
  // completed onboarding in *this* render, and we must not bounce
  // the operator out before they save their codes.
  useEffect(() => {
    if (status && !status.first_run_required && step !== 'recovery_codes') {
      navigate('/', { replace: true });
    }
  }, [status, navigate, step]);

  const defaultDir = status?.data_dir ?? null;
  const changed =
    chosenDir !== null && defaultDir !== null && chosenDir !== defaultDir;

  async function handlePickDifferent(): Promise<void> {
    setDirError('');
    try {
      const picked = await pickDirectory();
      if (!picked) return;
      const result = await check.mutateAsync({
        path: picked,
        estimatedBatchSize: 0,
      });
      if (!result.writable) {
        setDirError(
          result.writableReason ??
            'Selected directory is not writable by Loom.',
        );
        return;
      }
      await persistDataDirectory(picked);
      setChosenDir(picked);
    } catch (err) {
      setDirError(
        err instanceof Error ? err.message : 'Failed to validate directory',
      );
    }
  }

  function handleContinueFromDir(): void {
    setStep('admin');
  }

  const handleSubmit = async (e: React.FormEvent): Promise<void> => {
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
      // if the admin chose a new data dir, restart the backend so it
      // reopens under the new LOOM_DATA_DIR. the tauri bridge is a
      // no-op in plain web context.
      if (isLite && changed) {
        try {
          await restartBackend();
        } catch {
          // best-effort; surface-level failure is non-fatal here.
        }
      }
      // hold the operator on a "save your codes" step before
      // navigating into the app. the codes returned here are
      // plaintext and only exist in memory; once the user
      // acknowledges we drop the state and route to /.
      setRecoveryCodes(resp.password_recovery_codes);
      setStep('recovery_codes');
    } catch (err) {
      if (err instanceof Error) {
        const msg = err.message.toLowerCase();
        if (msg.includes('already completed')) {
          setError('This install is already set up. Redirecting to sign in.');
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
          </p>
        </header>

        {isLite && step === 'data_dir' && (
          <section
            aria-labelledby="data-dir-heading"
            className="space-y-4"
            data-testid="first-run-data-dir"
          >
            <div>
              <h2
                id="data-dir-heading"
                className="text-lg font-semibold text-foreground"
              >
                Pick a data directory
              </h2>
              <p className="text-sm text-muted-foreground">
                Loom stores originals, derivatives, and its SQLite database
                under this folder. Pick an external drive if you expect large
                case files.
              </p>
            </div>

            <div className="rounded-md border border-border bg-muted/40 p-3 text-sm">
              <p className="text-muted-foreground">Current data directory</p>
              <p
                className="break-all font-mono text-foreground"
                data-testid="chosen-data-dir"
              >
                {chosenDir ?? defaultDir ?? '(unset)'}
              </p>
            </div>

            {dirError && (
              <p role="alert" className="text-sm text-destructive">
                {dirError}
              </p>
            )}

            {changed && (
              <p className="rounded-md border border-border bg-muted/40 p-2 text-xs text-muted-foreground">
                Requires restart to take effect — we&apos;ll restart after you
                finish setup.
              </p>
            )}

            <div className="flex flex-col gap-2 sm:flex-row">
              <button
                type="button"
                onClick={handleContinueFromDir}
                className="flex-1 rounded-md bg-primary px-4 py-2 text-primary-foreground hover:bg-primary/90"
              >
                Use this directory
              </button>
              <button
                type="button"
                onClick={handlePickDifferent}
                disabled={check.isPending}
                className="flex-1 rounded-md border border-border bg-background px-4 py-2 text-foreground hover:bg-accent disabled:opacity-50"
              >
                {check.isPending ? 'Validating…' : 'Pick different directory…'}
              </button>
            </div>
          </section>
        )}

        {step === 'admin' && (
          <>
            <p className="text-center text-sm text-muted-foreground">
              Let&apos;s set up your admin account.
            </p>

            {isLite && chosenDir && (
              <div className="rounded-md border border-border bg-muted/40 p-3 text-sm">
                <p className="text-muted-foreground">Data directory</p>
                <p className="break-all font-mono text-foreground">
                  {chosenDir}
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
                {complete.isPending
                  ? 'Creating account…'
                  : 'Create admin account'}
              </button>
            </form>
          </>
        )}

        {step === 'recovery_codes' && (
          <RecoveryCodesPanel
            codes={recoveryCodes}
            onAcknowledge={() => {
              // drop the plaintext codes from memory before routing
              // out; even though react will gc the state, this makes
              // the lifecycle obvious to anyone reading the source.
              setRecoveryCodes([]);
              navigate('/', { replace: true });
            }}
          />
        )}
      </div>
    </div>
  );
}
