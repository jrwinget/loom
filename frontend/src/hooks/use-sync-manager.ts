import { useCallback, useEffect, useRef, useState } from 'react';
import { processQueue } from '@/lib/offline-client';
import { useOfflineQueueStore } from '@/stores/offline-queue-store';
import { useToastStore } from '@/stores/toast-store';

interface SyncManagerResult {
  isSyncing: boolean;
  queueLength: number;
  syncErrors: string[];
  retrySync: () => void;
}

export function useSyncManager(): SyncManagerResult {
  const [isSyncing, setIsSyncing] = useState(false);
  const [syncErrors, setSyncErrors] = useState<string[]>([]);
  const syncingRef = useRef(false);

  const queue = useOfflineQueueStore((s) => s.queue);
  const queueLength = queue.filter(
    (i) => i.status === 'pending' || i.status === 'failed',
  ).length;

  const sync = useCallback(async () => {
    if (syncingRef.current) return;
    if (!navigator.onLine) return;

    const pending = useOfflineQueueStore.getState().getPending();
    if (pending.length === 0) return;

    syncingRef.current = true;
    setIsSyncing(true);
    setSyncErrors([]);

    useToastStore.getState().addToast({
      type: 'info',
      message:
        `Syncing ${pending.length} offline ` +
        `change${pending.length === 1 ? '' : 's'}...`,
    });

    const result = await processQueue();

    if (result.processed > 0) {
      useToastStore.getState().addToast({
        type: 'success',
        message:
          `Synced ${result.processed} ` +
          `change${result.processed === 1 ? '' : 's'}`,
      });
    }

    if (result.failed > 0) {
      const failedItems = useOfflineQueueStore
        .getState()
        .queue.filter((i) => i.status === 'failed');
      const errors = failedItems
        .map((i) => i.error ?? 'Unknown error')
        .filter(Boolean);
      setSyncErrors(errors);

      useToastStore.getState().addToast({
        type: 'error',
        message:
          `${result.failed} ` +
          `change${result.failed === 1 ? '' : 's'} ` +
          'failed to sync. Check the queue for details.',
        duration: 0,
      });
    }

    setIsSyncing(false);
    syncingRef.current = false;
  }, []);

  // sync when coming back online
  useEffect(() => {
    const handleOnline = (): void => {
      void sync();
    };

    window.addEventListener('online', handleOnline);
    return () => {
      window.removeEventListener('online', handleOnline);
    };
  }, [sync]);

  // also try to sync on mount if there are pending items
  useEffect(() => {
    if (navigator.onLine && queueLength > 0) {
      void sync();
    }
    // only run on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    isSyncing,
    queueLength,
    syncErrors,
    retrySync: sync,
  };
}
