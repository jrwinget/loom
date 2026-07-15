import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FactoryResetDialog } from '@/components/auth/FactoryResetDialog';
import { RecoveryCodesPanel } from '@/components/auth/RecoveryCodesPanel';
import { apiClient } from '@/lib/api-client';
import {
  isTauri,
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

  const {
    data: status,
    isLoading,
    isError,
    refetch: refetchStatus,
  } = useFirstRunStatus();
  const complete = useCompleteFirstRun();
  const check = useStorageCheck();

  // server-profile installs skip the data-dir step entirely.
  const isLite = status?.deploymentProfile === 'lite';

  const [step, setStep] = useState<Step>('admin');
  const [chosenDir, setChosenDir] = useState<string | null>(null);
  const [stepInitialized, setStepInitialized] = useState(false);
  const [dirError, setDirError] = useState('');
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [error, setError] = useState('');
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [resetOpen, setResetOpen] = useState(false);
  const [switching, setSwitching] = useState(false);

  // pick the initial step once the status payload arrives. done during
  // render so the first paint already reflects the right step.
  if (!stepInitialized && status && status.firstRunRequired) {
    setStepInitialized(true);
    setStep(isLite ? 'data_dir' : 'admin');
    if (isLite && !chosenDir) {
      setChosenDir(status.dataDir ?? null);
    }
  }

  // already-onboarded installs should not see this page. the ref
  // guards the operator who is onboarding right now: the complete
  // mutation flips the cached firstRunRequired to false while
  // handleSubmit is still awaiting /auth/me (step is still 'admin'),
  // and without it this effect would bounce them to / before the
  // recovery_codes step — the only time the plaintext codes exist.
  const onboardingRef = useRef(false);
  useEffect(() => {
    if (
      status &&
      !status.firstRunRequired &&
      step !== 'recovery_codes' &&
      !onboardingRef.current
    ) {
      navigate('/', { replace: true });
    }
  }, [status, navigate, step]);

  const defaultDir = status?.dataDir ?? null;
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

  async function handleContinueFromDir(): Promise<void> {
    setDirError('');
    // switch the sidecar onto the chosen dir BEFORE creating the admin,
    // so the bootstrap user lands in the final database. restartBackend
    // resolves only once the new sidecar passes /health, so awaiting it
    // is the readiness signal; then refetch status against the new dir.
    if (isLite && changed) {
      setSwitching(true);
      try {
        await persistDataDirectory(chosenDir!);
        await restartBackend();
        await refetchStatus();
      } catch (err) {
        setDirError(
          err instanceof Error
            ? err.message
            : 'Failed to switch data directory',
        );
        return;
      } finally {
        setSwitching(false);
      }
    }
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
      onboardingRef.current = true;
      const resp = await complete.mutateAsync({
        admin_email: email,
        admin_password: password,
        admin_full_name: fullName,
      });
      // stash the token so /auth/me can identify the new admin.
      useAuthStore.setState({ token: resp.accessToken });
      const user = await apiClient.get<User>('/auth/me');
      setAuth(resp.accessToken, user);
      // the data dir was already switched (and the sidecar restarted)
      // before this step, so the admin we just created lives in the
      // final database — nothing to restart here.
      //
      // hold the operator on a "save your codes" step before
      // navigating into the app. the codes returned here are
      // plaintext and only exist in memory; once the user
      // acknowledges we drop the state and route to /.
      setRecoveryCodes(resp.passwordRecoveryCodes);
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
        <div className="border-border bg-card w-full max-w-sm space-y-4 rounded-lg border p-8 text-center">
          <p
            role="alert"
            className="text-destructive text-sm"
            data-testid="first-run-error"
          >
            Couldn&apos;t reach the backend. If this persists, restart Loom or
            reset this install.
          </p>
          {isTauri && (
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
        {isTauri && (
          <FactoryResetDialog
            open={resetOpen}
            onClose={() => setResetOpen(false)}
            onSuccess={() => {
              setResetOpen(false);
              // sidecar respawns into a fresh first-run state; remount
              // this page so the new instance answers /first-run/status.
              navigate('/first-run', { replace: true });
            }}
          />
        )}
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-12">
      <div className="border-border bg-card w-full max-w-lg space-y-6 rounded-lg border p-8">
        <header className="space-y-2 text-center">
          <h1 className="text-foreground text-2xl font-bold">
            Welcome to Loom
          </h1>
          <p className="text-muted-foreground text-sm">
            Loom combines source documents into defensible event timelines.
          </p>
          <p className="text-muted-foreground text-xs">
            If your system warned you when installing: that is the standard
            notice for community-built software that ships without paid OS
            certificates. Every release includes checksums so you can verify
            your download.
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
                className="text-foreground text-lg font-semibold"
              >
                Pick a data directory
              </h2>
              <p className="text-muted-foreground text-sm">
                Loom stores originals, derivatives, and its SQLite database
                under this folder. Pick an external drive if you expect large
                case files.
              </p>
            </div>

            <div className="border-border bg-muted/40 rounded-md border p-3 text-sm">
              <p className="text-muted-foreground">Current data directory</p>
              <p
                className="text-foreground font-mono break-all"
                data-testid="chosen-data-dir"
              >
                {chosenDir ?? defaultDir ?? '(unset)'}
              </p>
            </div>

            {dirError && (
              <p role="alert" className="text-destructive text-sm">
                {dirError}
              </p>
            )}

            {changed && (
              <p className="border-border bg-muted/40 text-muted-foreground rounded-md border p-2 text-xs">
                Loom will switch to this directory when you continue.
              </p>
            )}

            <div className="flex flex-col gap-2 sm:flex-row">
              <button
                type="button"
                onClick={handleContinueFromDir}
                disabled={switching || check.isPending}
                className="bg-primary text-primary-foreground hover:bg-primary/90 flex-1 rounded-md px-4 py-2 disabled:opacity-50"
              >
                {switching ? 'Switching…' : 'Use this directory'}
              </button>
              <button
                type="button"
                onClick={handlePickDifferent}
                disabled={switching || check.isPending}
                className="border-border bg-background text-foreground hover:bg-accent flex-1 rounded-md border px-4 py-2 disabled:opacity-50"
              >
                {check.isPending ? 'Validating…' : 'Pick different directory…'}
              </button>
            </div>
          </section>
        )}

        {step === 'admin' && (
          <>
            <p className="text-muted-foreground text-center text-sm">
              Let&apos;s set up your admin account.
            </p>

            {isLite && chosenDir && (
              <div className="border-border bg-muted/40 rounded-md border p-3 text-sm">
                <p className="text-muted-foreground">Data directory</p>
                <p className="text-foreground font-mono break-all">
                  {chosenDir}
                </p>
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4" noValidate>
              <div>
                <label
                  htmlFor="fullName"
                  className="text-foreground block text-sm font-medium"
                >
                  Full name
                </label>
                <input
                  id="fullName"
                  type="text"
                  autoComplete="name"
                  value={fullName}
                  onChange={(e) => setFullName(e.target.value)}
                  className="border-input bg-background text-foreground mt-1 block w-full rounded-md border px-3 py-2"
                  required
                  minLength={1}
                />
              </div>
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
                  Password (minimum {MIN_PASSWORD_LENGTH} characters)
                </label>
                <input
                  id="password"
                  type="password"
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="border-input bg-background text-foreground mt-1 block w-full rounded-md border px-3 py-2"
                  required
                  minLength={MIN_PASSWORD_LENGTH}
                />
              </div>
              <div>
                <label
                  htmlFor="confirm"
                  className="text-foreground block text-sm font-medium"
                >
                  Confirm password
                </label>
                <input
                  id="confirm"
                  type="password"
                  autoComplete="new-password"
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
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
                disabled={complete.isPending}
                className="bg-primary text-primary-foreground w-full rounded-md px-4 py-2 disabled:opacity-50"
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
