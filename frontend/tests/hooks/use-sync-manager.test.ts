import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useSyncManager } from '@/hooks/use-sync-manager';
import { useOfflineQueueStore } from '@/stores/offline-queue-store';

const processQueue = vi.fn();
vi.mock('@/lib/offline-client', () => ({
  processQueue: () => processQueue(),
}));

const addToast = vi.fn();
vi.mock('@/stores/toast-store', () => ({
  useToastStore: { getState: () => ({ addToast }) },
}));

function setOnline(value: boolean): void {
  Object.defineProperty(navigator, 'onLine', {
    configurable: true,
    value,
  });
}

function enqueuePending(): string {
  return useOfflineQueueStore.getState().enqueue({
    type: 'event',
    payload: { method: 'POST', path: '/cases/case-1/events' },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  useOfflineQueueStore.setState({ queue: [] });
  setOnline(true);
});

afterEach(() => {
  setOnline(true);
});

describe('useSyncManager', () => {
  it('counts pending and failed items in the queue length', () => {
    setOnline(false);
    enqueuePending();
    enqueuePending();
    const failedId = enqueuePending();
    useOfflineQueueStore.getState().markFailed(failedId, 'boom');

    const { result } = renderHook(() => useSyncManager());

    expect(result.current.queueLength).toBe(3);
  });

  it('syncs pending changes on mount and reports success', async () => {
    enqueuePending();
    processQueue.mockResolvedValue({ processed: 1, failed: 0 });

    renderHook(() => useSyncManager());

    await waitFor(() => expect(processQueue).toHaveBeenCalled());
    expect(addToast).toHaveBeenCalledWith({
      type: 'success',
      message: 'Synced 1 change',
    });
  });

  it('does not sync while offline', () => {
    setOnline(false);
    enqueuePending();

    const { result } = renderHook(() => useSyncManager());
    act(() => {
      result.current.retrySync();
    });

    expect(processQueue).not.toHaveBeenCalled();
  });

  it('collects the error messages of items that fail to sync', async () => {
    const id = enqueuePending();
    processQueue.mockImplementation(async () => {
      useOfflineQueueStore.getState().markFailed(id, 'network down');
      return { processed: 0, failed: 1 };
    });

    const { result } = renderHook(() => useSyncManager());

    await waitFor(() =>
      expect(result.current.syncErrors).toContain('network down'),
    );
  });
});
