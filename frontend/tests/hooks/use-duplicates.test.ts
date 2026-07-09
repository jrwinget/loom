import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  useDuplicates,
  useScanDuplicates,
  useUpdateCluster,
} from '@/hooks/use-duplicates';
import type { DuplicateCluster } from '@/types/transcript';

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
  },
}));

const cluster: DuplicateCluster = {
  id: 'cluster-1',
  caseId: 'case-1',
  status: 'pending',
  members: [],
  createdAt: '2026-01-01T00:00:00Z',
};

function createWrapper(): ({
  children,
}: {
  children: React.ReactNode;
}) => React.ReactElement {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return ({ children }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useDuplicates', () => {
  it('unwraps the clusters array from the response envelope', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      clusters: [cluster],
      total: 1,
    });

    const { result } = renderHook(() => useDuplicates('case-1'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([cluster]);
  });

  it('is disabled when caseId is empty', () => {
    const { result } = renderHook(() => useDuplicates(''), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('useScanDuplicates', () => {
  it('posts to the scan endpoint for the case', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.post).mockResolvedValueOnce({ taskId: 'task-1' });

    const { result } = renderHook(() => useScanDuplicates('case-1'), {
      wrapper: createWrapper(),
    });
    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(vi.mocked(apiClient.post)).toHaveBeenCalledWith(
      '/cases/case-1/duplicates/scan',
    );
  });
});

describe('useUpdateCluster', () => {
  it('patches the cluster with a snake_case primary asset id', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.patch).mockResolvedValueOnce(cluster);

    const { result } = renderHook(() => useUpdateCluster(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({
      caseId: 'case-1',
      clusterId: 'cluster-1',
      status: 'reviewed',
      primaryAssetId: 'asset-9',
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(vi.mocked(apiClient.patch)).toHaveBeenCalledWith(
      '/cases/case-1/duplicates/cluster-1',
      { status: 'reviewed', primary_asset_id: 'asset-9' },
    );
  });
});
