import { apiClient } from '@/lib/api-client';
import { useOfflineQueueStore } from '@/stores/offline-queue-store';
import type { QueueItemType } from '@/stores/offline-queue-store';

const MAX_RETRIES = 3;

function idempotencyKey(
  method: string,
  path: string,
  body?: string,
): string {
  // simple djb2 hash for body dedup
  let hash = 5381;
  const str = body ?? '';
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) + hash + str.charCodeAt(i)) | 0;
  }
  return `${method}:${path}:${hash}`;
}

class OfflineError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'OfflineError';
  }
}

// infer the queue item type from the api path
function inferType(path: string): QueueItemType {
  if (path.includes('/annotations')) return 'annotation';
  if (path.includes('/timeline')) return 'event';
  return 'upload';
}

function isOnline(): boolean {
  return typeof navigator !== 'undefined' ? navigator.onLine : true;
}

function enqueueMutation(
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE',
  path: string,
  body?: unknown,
): string {
  const store = useOfflineQueueStore.getState();
  const serialized = body ? JSON.stringify(body) : undefined;
  const key = idempotencyKey(method, path, serialized);

  // deduplicate: skip if an identical pending item exists
  const existing = store.getPending().find(
    (item) =>
      idempotencyKey(
        item.payload.method,
        item.payload.path,
        item.payload.body,
      ) === key,
  );
  if (existing) return existing.id;

  return store.enqueue({
    type: inferType(path),
    payload: {
      method,
      path,
      body: serialized,
    },
  });
}

export const offlineClient = {
  get: <T>(path: string): Promise<T> => {
    if (!isOnline()) {
      return Promise.reject(
        new OfflineError('You are offline. Cannot fetch data.'),
      );
    }
    return apiClient.get<T>(path);
  },

  post: <T>(path: string, body?: unknown): Promise<T> => {
    if (!isOnline()) {
      const id = enqueueMutation('POST', path, body);
      // return a placeholder that indicates queuing
      return Promise.resolve({
        _offlineQueued: true,
        _queueId: id,
      } as T);
    }
    return apiClient.post<T>(path, body);
  },

  patch: <T>(path: string, body?: unknown): Promise<T> => {
    if (!isOnline()) {
      const id = enqueueMutation('PATCH', path, body);
      return Promise.resolve({
        _offlineQueued: true,
        _queueId: id,
      } as T);
    }
    return apiClient.patch<T>(path, body);
  },

  delete: <T>(path: string): Promise<T> => {
    if (!isOnline()) {
      const id = enqueueMutation('DELETE', path);
      return Promise.resolve({
        _offlineQueued: true,
        _queueId: id,
      } as T);
    }
    return apiClient.delete<T>(path);
  },
} as const;

// process the offline queue in fifo order
export async function processQueue(): Promise<{
  processed: number;
  failed: number;
}> {
  const store = useOfflineQueueStore.getState();
  const pending = store.getPending();
  let processed = 0;
  let failed = 0;

  for (const item of pending) {
    if (!isOnline()) break;
    if (item.retryCount >= MAX_RETRIES) {
      failed += 1;
      continue;
    }

    store.markSyncing(item.id);

    try {
      const { method, path, body } = item.payload;
      const parsed = body ? JSON.parse(body) : undefined;

      switch (method) {
        case 'POST':
          await apiClient.post(path, parsed);
          break;
        case 'PUT':
          // use post as a fallback — api client has no put
          await apiClient.post(path, parsed);
          break;
        case 'PATCH':
          await apiClient.patch(path, parsed);
          break;
        case 'DELETE':
          await apiClient.delete(path);
          break;
      }

      store.dequeue(item.id);
      processed += 1;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown sync error';
      store.markFailed(item.id, message);
      failed += 1;
    }
  }

  return { processed, failed };
}
