import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type QueueItemType = 'upload' | 'annotation' | 'event';

export type QueueItemStatus = 'pending' | 'syncing' | 'failed';

export interface OfflineQueueItem {
  id: string;
  type: QueueItemType;
  payload: {
    method: 'POST' | 'PUT' | 'PATCH' | 'DELETE';
    path: string;
    body?: string;
  };
  createdAt: number;
  status: QueueItemStatus;
  retryCount: number;
  error?: string;
}

interface OfflineQueueState {
  queue: OfflineQueueItem[];
  enqueue: (
    item: Omit<OfflineQueueItem, 'id' | 'createdAt' | 'status' | 'retryCount'>,
  ) => string;
  dequeue: (id: string) => void;
  markSyncing: (id: string) => void;
  markFailed: (id: string, error: string) => void;
  resetItem: (id: string) => void;
  getQueue: () => OfflineQueueItem[];
  getPending: () => OfflineQueueItem[];
  clearCompleted: () => void;
}

let nextId = 0;
function uid(): string {
  nextId += 1;
  return `oq-${Date.now()}-${nextId}`;
}

export const useOfflineQueueStore = create<OfflineQueueState>()(
  persist(
    (set, get) => ({
      queue: [],

      enqueue: (item) => {
        const id = uid();
        const entry: OfflineQueueItem = {
          ...item,
          id,
          createdAt: Date.now(),
          status: 'pending',
          retryCount: 0,
        };
        set((s) => ({
          queue: [...s.queue, entry],
        }));
        return id;
      },

      dequeue: (id) =>
        set((s) => ({
          queue: s.queue.filter((i) => i.id !== id),
        })),

      markSyncing: (id) =>
        set((s) => ({
          queue: s.queue.map((i) =>
            i.id === id ? { ...i, status: 'syncing' as const } : i,
          ),
        })),

      markFailed: (id, error) =>
        set((s) => ({
          queue: s.queue.map((i) =>
            i.id === id
              ? {
                  ...i,
                  status: 'failed' as const,
                  retryCount: i.retryCount + 1,
                  error,
                }
              : i,
          ),
        })),

      resetItem: (id) =>
        set((s) => ({
          queue: s.queue.map((i) =>
            i.id === id
              ? {
                  ...i,
                  status: 'pending' as const,
                  error: undefined,
                }
              : i,
          ),
        })),

      getQueue: () => get().queue,

      getPending: () => get().queue.filter((i) => i.status === 'pending'),

      clearCompleted: () =>
        set((s) => ({
          queue: s.queue.filter(
            (i) => i.status === 'pending' || i.status === 'syncing',
          ),
        })),
    }),
    {
      name: 'loom-offline-queue',
      version: 1,
    },
  ),
);
