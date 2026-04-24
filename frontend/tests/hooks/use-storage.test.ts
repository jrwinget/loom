import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  useRelocateStorage,
  useRelocationJob,
  useStorageCheck,
  useStorageUsage,
} from '@/hooks/use-storage';

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('@/stores/auth-store', () => ({
  useAuthStore: {
    getState: () => ({ token: 'test-token' }),
  },
}));

vi.mock('@/stores/toast-store', () => ({
  useToastStore: {
    getState: () => ({ addToast: vi.fn() }),
  },
}));

function createWrapper(): ({
  children,
}: {
  children: React.ReactNode;
}) => React.ReactElement {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return ({ children }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

describe('useStorageUsage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('maps wire response to camelCase ui shape', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      data_dir: '/var/loom',
      free_bytes: 10,
      total_bytes: 100,
      originals_bytes: 5,
      derivatives_bytes: 3,
      db_bytes: 1,
      logs_bytes: 1,
      asset_count: 42,
      on_system_drive: true,
    });

    const { result } = renderHook(() => useStorageUsage(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({
      dataDir: '/var/loom',
      freeBytes: 10,
      totalBytes: 100,
      originalsBytes: 5,
      derivativesBytes: 3,
      dbBytes: 1,
      logsBytes: 1,
      assetCount: 42,
      onSystemDrive: true,
    });
  });

  it('is disabled when enabled=false', () => {
    const { result } = renderHook(
      () => useStorageUsage({ enabled: false }),
      { wrapper: createWrapper() },
    );
    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('useStorageCheck', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('posts with estimated_batch_size snake-case and maps result', async () => {
    const { apiClient } = await import('@/lib/api-client');
    const postMock = vi.mocked(apiClient.post);
    postMock.mockResolvedValueOnce({
      writable: true,
      writable_reason: null,
      free_bytes: 100,
      total_bytes: 200,
      on_system_drive: false,
      advisory: 'warning',
      advisory_reason: 'low free space',
    });

    const { result } = renderHook(() => useStorageCheck(), {
      wrapper: createWrapper(),
    });

    const mapped = await result.current.mutateAsync({
      path: '/tmp/loom',
      estimatedBatchSize: 1024,
    });

    expect(postMock).toHaveBeenCalledWith('/storage/check', {
      path: '/tmp/loom',
      estimated_batch_size: 1024,
    });
    expect(mapped.advisory).toBe('warning');
    expect(mapped.advisoryReason).toBe('low free space');
    expect(mapped.freeBytes).toBe(100);
  });
});

describe('useRelocateStorage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('returns the job id from an accepted response', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      job_id: 'job-abc',
    });

    const { result } = renderHook(() => useRelocateStorage(), {
      wrapper: createWrapper(),
    });

    const jobId = await result.current.mutateAsync({
      targetPath: '/mnt/evidence',
    });
    expect(jobId).toBe('job-abc');
  });
});

describe('useRelocationJob', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('is disabled when jobId is null', () => {
    const { result } = renderHook(() => useRelocationJob(null), {
      wrapper: createWrapper(),
    });
    expect(result.current.fetchStatus).toBe('idle');
  });

  it('maps wire job response', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      job_id: 'job-xyz',
      status: 'completed',
      assets_copied: 10,
      assets_total: 10,
      bytes_copied: 500,
      bytes_total: 500,
      error: null,
      started_at: '2026-04-24T00:00:00Z',
      completed_at: '2026-04-24T00:05:00Z',
    });

    const { result } = renderHook(() => useRelocationJob('job-xyz'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.status).toBe('completed');
    expect(result.current.data?.assetsCopied).toBe(10);
  });
});
