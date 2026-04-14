import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest';
import {
  useOfflineQueueStore,
} from '@/stores/offline-queue-store';

// mock navigator.onLine to force offline
function setOffline(offline: boolean) {
  Object.defineProperty(navigator, 'onLine', {
    value: !offline,
    writable: true,
    configurable: true,
  });
}

// mock api-client so we don't make real requests
vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

describe('offline-client deduplication', () => {
  beforeEach(() => {
    useOfflineQueueStore.setState({ queue: [] });
    setOffline(true);
  });

  afterEach(() => {
    setOffline(false);
    localStorage.clear();
  });

  it('deduplicates identical mutations in the queue', async () => {
    // dynamic import so mocks are resolved
    const { offlineClient } = await import(
      '@/lib/offline-client'
    );

    await offlineClient.post('/cases/1/annotations', {
      text: 'duplicate',
    });
    await offlineClient.post('/cases/1/annotations', {
      text: 'duplicate',
    });

    const pending = useOfflineQueueStore
      .getState()
      .getPending();
    expect(pending).toHaveLength(1);
  });

  it('allows different mutations to be queued', async () => {
    const { offlineClient } = await import(
      '@/lib/offline-client'
    );

    await offlineClient.post('/cases/1/annotations', {
      text: 'first',
    });
    await offlineClient.post('/cases/1/annotations', {
      text: 'second',
    });

    const pending = useOfflineQueueStore
      .getState()
      .getPending();
    expect(pending).toHaveLength(2);
  });

  it('allows same path with different methods', async () => {
    const { offlineClient } = await import(
      '@/lib/offline-client'
    );

    await offlineClient.post('/cases/1/annotations', {
      text: 'create',
    });
    await offlineClient.patch('/cases/1/annotations', {
      text: 'create',
    });

    const pending = useOfflineQueueStore
      .getState()
      .getPending();
    expect(pending).toHaveLength(2);
  });

  it('returns existing queue id for duplicates', async () => {
    const { offlineClient } = await import(
      '@/lib/offline-client'
    );

    const result1 = await offlineClient.post(
      '/cases/1/annotations',
      { text: 'same' },
    );
    const result2 = await offlineClient.post(
      '/cases/1/annotations',
      { text: 'same' },
    );

    // both should reference the same queue id
    const id1 = (
      result1 as { _queueId: string }
    )._queueId;
    const id2 = (
      result2 as { _queueId: string }
    )._queueId;
    expect(id1).toBe(id2);
  });
});
