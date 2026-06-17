import * as Dialog from '@radix-ui/react-dialog';
import { useEffect, useState } from 'react';
import { useFirstRunStatus } from '@/hooks/use-first-run';
import {
  useRelocateStorage,
  useRelocationJob,
  useStorageCheck,
  useStorageUsage,
} from '@/hooks/use-storage';
import { formatBytes } from '@/lib/format';
import {
  persistDataDirectory,
  pickDirectory,
  restartBackend,
} from '@/lib/tauri-bridge';
import { useToastStore } from '@/stores/toast-store';
import type { StorageCheckResult, StorageUsage } from '@/types/storage';

function UsageRow(props: { label: string; bytes: number }): React.ReactElement {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="text-muted-foreground">{props.label}</span>
      <span className="font-mono text-foreground">
        {formatBytes(props.bytes)}
      </span>
    </div>
  );
}

function UsageCard(props: {
  usage: StorageUsage;
  onOpenMove: () => void;
}): React.ReactElement {
  const { usage, onOpenMove } = props;
  const usedBytes = Math.max(usage.totalBytes - usage.freeBytes, 0);

  return (
    <div className="bg-card space-y-4 rounded-lg border border-border p-6">
      <div>
        <p className="text-sm text-muted-foreground">Data directory</p>
        <p
          className="break-all font-mono text-sm text-foreground"
          data-testid="current-data-dir"
        >
          {usage.dataDir}
        </p>
      </div>

      {usage.onSystemDrive && (
        <p
          role="alert"
          className="border-warning/50 bg-warning/10 rounded-md border p-2 text-xs text-foreground"
        >
          Data is on the system drive — consider moving to a dedicated drive for
          large case files.
        </p>
      )}

      <div className="space-y-2">
        <UsageRow label="Originals" bytes={usage.originalsBytes} />
        <UsageRow label="Derivatives" bytes={usage.derivativesBytes} />
        <UsageRow label="Database" bytes={usage.dbBytes} />
        <UsageRow label="Logs" bytes={usage.logsBytes} />
        <UsageRow label="Used on drive" bytes={usedBytes} />
        <UsageRow label="Free on drive" bytes={usage.freeBytes} />
      </div>

      <div className="flex items-center justify-between border-t border-border pt-4 text-sm">
        <span className="text-muted-foreground">
          {usage.assetCount.toLocaleString()} assets
        </span>
        <button
          type="button"
          onClick={onOpenMove}
          className="rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground hover:bg-primary/90"
        >
          Move data directory…
        </button>
      </div>
    </div>
  );
}

function MoveDialog(props: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currentPath: string;
}): React.ReactElement {
  const { open, onOpenChange, currentPath } = props;
  const check = useStorageCheck();
  const relocate = useRelocateStorage();

  const [target, setTarget] = useState<string | null>(null);
  const [checkResult, setCheckResult] = useState<StorageCheckResult | null>(
    null,
  );
  const [jobId, setJobId] = useState<string | null>(null);
  const [pickError, setPickError] = useState('');
  const [wasOpen, setWasOpen] = useState(open);

  const job = useRelocationJob(jobId);
  const addToast = useToastStore((s) => s.addToast);

  // reset local state during render on each open transition so a
  // reopened dialog starts clean.
  if (open && !wasOpen) {
    setWasOpen(true);
    setTarget(null);
    setCheckResult(null);
    setJobId(null);
    setPickError('');
  } else if (!open && wasOpen) {
    setWasOpen(false);
  }

  // mutation caches live outside react state, so clear them in an
  // effect when the dialog opens.
  useEffect(() => {
    if (open) {
      check.reset();
      relocate.reset();
    }
    // identities of check/relocate change every render; only the open
    // transition should trigger a reset.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  // once the job completes, toast + restart the backend so the
  // sidecar reopens under the new LOOM_DATA_DIR.
  useEffect(() => {
    if (!job.data || !target) return;
    if (job.data.status === 'completed') {
      addToast({
        type: 'success',
        message: 'Move complete — restarting to use new directory',
      });
      void (async () => {
        try {
          await persistDataDirectory(target);
          await restartBackend();
        } catch (err) {
          addToast({
            type: 'error',
            message:
              err instanceof Error
                ? err.message
                : 'Failed to restart backend after move',
          });
        }
      })();
      onOpenChange(false);
    } else if (job.data.status === 'failed') {
      addToast({
        type: 'error',
        message: job.data.error ?? 'Storage move failed',
      });
    }
  }, [job.data, target, addToast, onOpenChange]);

  async function handlePick(): Promise<void> {
    setPickError('');
    setCheckResult(null);
    try {
      const picked = await pickDirectory();
      if (!picked) return;
      if (picked === currentPath) {
        setPickError('Pick a different directory from the current one.');
        return;
      }
      setTarget(picked);
      const result = await check.mutateAsync({
        path: picked,
        estimatedBatchSize: 0,
      });
      setCheckResult(result);
    } catch (err) {
      setPickError(
        err instanceof Error ? err.message : 'Failed to validate directory',
      );
    }
  }

  function handleConfirm(): void {
    if (!target || !checkResult?.writable) return;
    relocate.mutate(
      { targetPath: target },
      {
        onSuccess: (id) => setJobId(id),
      },
    );
  }

  const inProgress = job.data?.status === 'running';
  const canConfirm =
    !!target &&
    checkResult?.writable === true &&
    checkResult.advisory !== 'blocked' &&
    !relocate.isPending &&
    !inProgress;

  const progressPct = job.data?.bytesTotal
    ? Math.min(
        100,
        Math.round((job.data.bytesCopied / job.data.bytesTotal) * 100),
      )
    : 0;

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="bg-card fixed left-1/2 top-1/2 w-full max-w-md -translate-x-1/2 -translate-y-1/2 space-y-4 rounded-lg border border-border p-6 shadow-lg">
          <Dialog.Title className="text-lg font-semibold text-foreground">
            Move data directory
          </Dialog.Title>
          <Dialog.Description className="text-sm text-muted-foreground">
            Pick a new directory. Loom will copy originals, derivatives, and the
            database over, verify hashes, then restart.
          </Dialog.Description>

          <div className="space-y-2 text-sm">
            <p className="text-muted-foreground">Current</p>
            <p className="break-all rounded-md border border-border bg-muted/40 p-2 font-mono text-foreground">
              {currentPath}
            </p>
          </div>

          <div className="space-y-2 text-sm">
            <p className="text-muted-foreground">Target</p>
            <div className="flex items-center gap-2">
              <p
                className="flex-1 break-all rounded-md border border-border bg-muted/40 p-2 font-mono text-foreground"
                data-testid="move-target-path"
              >
                {target ?? '(none selected)'}
              </p>
              <button
                type="button"
                onClick={handlePick}
                disabled={check.isPending || inProgress}
                className="rounded-md border border-border bg-background px-3 py-2 text-xs text-foreground hover:bg-accent disabled:opacity-50"
              >
                {check.isPending ? 'Checking…' : 'Pick…'}
              </button>
            </div>
          </div>

          {pickError && (
            <p role="alert" className="text-sm text-destructive">
              {pickError}
            </p>
          )}

          {checkResult && (
            <div
              data-testid="move-check-result"
              className="space-y-1 rounded-md border border-border bg-muted/40 p-3 text-xs"
            >
              <p>
                Writable:{' '}
                <span
                  className={
                    checkResult.writable
                      ? 'text-green-600 dark:text-green-400'
                      : 'text-destructive'
                  }
                >
                  {checkResult.writable ? 'yes' : 'no'}
                </span>
              </p>
              {!checkResult.writable && checkResult.writableReason && (
                <p className="text-muted-foreground">
                  {checkResult.writableReason}
                </p>
              )}
              <p>
                Free: {formatBytes(checkResult.freeBytes)} of{' '}
                {formatBytes(checkResult.totalBytes)}
              </p>
              <p>
                Advisory:{' '}
                <span className="font-medium">{checkResult.advisory}</span>
              </p>
              {checkResult.advisoryReason && (
                <p className="text-muted-foreground">
                  {checkResult.advisoryReason}
                </p>
              )}
            </div>
          )}

          {job.data && (
            <div className="space-y-2">
              <div
                role="progressbar"
                aria-valuenow={progressPct}
                aria-valuemin={0}
                aria-valuemax={100}
                aria-label="Storage move progress"
                className="h-2 w-full overflow-hidden rounded-full bg-muted"
              >
                <div
                  className="h-full bg-primary transition-all"
                  style={{ width: `${progressPct}%` }}
                />
              </div>
              <p className="text-xs text-muted-foreground">
                {job.data.assetsCopied} / {job.data.assetsTotal} assets,{' '}
                {formatBytes(job.data.bytesCopied)} /{' '}
                {formatBytes(job.data.bytesTotal)}
              </p>
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Dialog.Close asChild>
              <button
                type="button"
                disabled={inProgress}
                className="rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent disabled:opacity-50"
              >
                Cancel
              </button>
            </Dialog.Close>
            <button
              type="button"
              disabled={!canConfirm}
              onClick={handleConfirm}
              className="rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {inProgress
                ? 'Moving…'
                : relocate.isPending
                  ? 'Starting…'
                  : 'Move & verify'}
            </button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

export function StorageSettingsPage(): React.ReactElement {
  const { data: firstRun } = useFirstRunStatus();
  const isLite = firstRun?.deploymentProfile === 'lite';
  const usageQuery = useStorageUsage({ enabled: isLite });
  const [moveOpen, setMoveOpen] = useState(false);

  if (!isLite) {
    return (
      <div className="mx-auto max-w-2xl p-6">
        <h1 className="text-2xl font-bold text-foreground">Storage</h1>
        <p className="mt-2 text-muted-foreground">
          Storage management is only available on desktop (Lite) installs.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">Storage</h1>
        <p className="text-sm text-muted-foreground">
          Manage where Loom stores originals, derivatives, and its database.
        </p>
      </div>

      {usageQuery.isLoading && (
        <p className="text-muted-foreground">Loading storage usage…</p>
      )}
      {usageQuery.isError && (
        <p role="alert" className="text-destructive">
          Could not load storage usage.
        </p>
      )}
      {usageQuery.data && (
        <UsageCard
          usage={usageQuery.data}
          onOpenMove={() => setMoveOpen(true)}
        />
      )}

      {usageQuery.data && (
        <MoveDialog
          open={moveOpen}
          onOpenChange={setMoveOpen}
          currentPath={usageQuery.data.dataDir}
        />
      )}
    </div>
  );
}
