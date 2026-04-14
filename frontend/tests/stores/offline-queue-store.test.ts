import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
} from 'vitest';
import {
  useOfflineQueueStore,
} from '@/stores/offline-queue-store';

describe('offlineQueueStore', () => {
  beforeEach(() => {
    // reset the store before each test
    useOfflineQueueStore.setState({ queue: [] });
  });

  afterEach(() => {
    localStorage.clear();
  });

  it('starts with an empty queue', () => {
    const queue = useOfflineQueueStore.getState().getQueue();
    expect(queue).toEqual([]);
  });

  it('enqueues an item with correct defaults', () => {
    const store = useOfflineQueueStore.getState();
    const id = store.enqueue({
      type: 'annotation',
      payload: {
        method: 'POST',
        path: '/cases/1/annotations',
        body: '{"text":"test"}',
      },
    });

    const queue = store.getQueue();
    expect(queue).toHaveLength(1);
    expect(queue[0]).toMatchObject({
      id,
      type: 'annotation',
      status: 'pending',
      retryCount: 0,
      payload: {
        method: 'POST',
        path: '/cases/1/annotations',
        body: '{"text":"test"}',
      },
    });
    expect(queue[0].createdAt).toBeGreaterThan(0);
  });

  it('dequeues an item by id', () => {
    const store = useOfflineQueueStore.getState();
    const id = store.enqueue({
      type: 'event',
      payload: { method: 'POST', path: '/events' },
    });

    store.dequeue(id);
    expect(store.getQueue()).toHaveLength(0);
  });

  it('marks an item as syncing', () => {
    const store = useOfflineQueueStore.getState();
    const id = store.enqueue({
      type: 'upload',
      payload: { method: 'POST', path: '/assets' },
    });

    store.markSyncing(id);
    const item = useOfflineQueueStore
      .getState()
      .getQueue()
      .find((i) => i.id === id);
    expect(item?.status).toBe('syncing');
  });

  it('marks an item as failed with error', () => {
    const store = useOfflineQueueStore.getState();
    const id = store.enqueue({
      type: 'upload',
      payload: { method: 'POST', path: '/assets' },
    });

    store.markFailed(id, 'Network error');
    const item = useOfflineQueueStore
      .getState()
      .getQueue()
      .find((i) => i.id === id);
    expect(item?.status).toBe('failed');
    expect(item?.retryCount).toBe(1);
    expect(item?.error).toBe('Network error');
  });

  it('increments retry count on repeated failures', () => {
    const store = useOfflineQueueStore.getState();
    const id = store.enqueue({
      type: 'upload',
      payload: { method: 'POST', path: '/assets' },
    });

    store.markFailed(id, 'Error 1');
    store.markFailed(id, 'Error 2');

    const item = useOfflineQueueStore
      .getState()
      .getQueue()
      .find((i) => i.id === id);
    expect(item?.retryCount).toBe(2);
  });

  it('resets an item back to pending', () => {
    const store = useOfflineQueueStore.getState();
    const id = store.enqueue({
      type: 'event',
      payload: { method: 'PATCH', path: '/events/1' },
    });

    store.markFailed(id, 'Error');
    store.resetItem(id);

    const item = useOfflineQueueStore
      .getState()
      .getQueue()
      .find((i) => i.id === id);
    expect(item?.status).toBe('pending');
    expect(item?.error).toBeUndefined();
  });

  it('getPending returns only pending items', () => {
    const store = useOfflineQueueStore.getState();
    const id1 = store.enqueue({
      type: 'upload',
      payload: { method: 'POST', path: '/a' },
    });
    store.enqueue({
      type: 'upload',
      payload: { method: 'POST', path: '/b' },
    });

    store.markSyncing(id1);

    const pending = useOfflineQueueStore
      .getState()
      .getPending();
    expect(pending).toHaveLength(1);
    expect(pending[0].payload.path).toBe('/b');
  });

  it('clearCompleted removes failed items', () => {
    const store = useOfflineQueueStore.getState();
    const id1 = store.enqueue({
      type: 'upload',
      payload: { method: 'POST', path: '/a' },
    });
    store.enqueue({
      type: 'upload',
      payload: { method: 'POST', path: '/b' },
    });

    store.markFailed(id1, 'Error');
    store.clearCompleted();

    const queue = useOfflineQueueStore
      .getState()
      .getQueue();
    expect(queue).toHaveLength(1);
    expect(queue[0].payload.path).toBe('/b');
  });

  it('maintains fifo order', () => {
    const store = useOfflineQueueStore.getState();
    store.enqueue({
      type: 'upload',
      payload: { method: 'POST', path: '/first' },
    });
    store.enqueue({
      type: 'annotation',
      payload: { method: 'POST', path: '/second' },
    });
    store.enqueue({
      type: 'event',
      payload: { method: 'POST', path: '/third' },
    });

    const queue = useOfflineQueueStore
      .getState()
      .getQueue();
    expect(queue.map((i) => i.payload.path)).toEqual([
      '/first',
      '/second',
      '/third',
    ]);
  });
});
