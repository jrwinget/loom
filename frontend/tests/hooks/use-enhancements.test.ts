import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  NEUTRAL_PARAMS,
  useCreateEnhancement,
  useEnhancements,
  useSuggestEnhancement,
} from '@/hooks/use-enhancements';
import { useJobStore } from '@/stores/job-store';

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

function createWrapper(): ({
  children,
}: {
  children: React.ReactNode;
}) => React.ReactElement {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

describe('useEnhancements', () => {
  beforeEach(() => vi.clearAllMocks());

  it('unwraps the enhancements list', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      enhancements: [{ id: 'd1', downloadUrl: 'http://x', createdAt: '' }],
    });

    const { result } = renderHook(() => useEnhancements('c1', 'a1'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(apiClient.get).toHaveBeenCalledWith(
      '/cases/c1/assets/a1/enhancements',
    );
    expect(result.current.data).toHaveLength(1);
  });
});

describe('useSuggestEnhancement', () => {
  beforeEach(() => vi.clearAllMocks());

  it('calls the suggest endpoint', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      params: NEUTRAL_PARAMS,
      reasons: [],
    });

    const { result } = renderHook(() => useSuggestEnhancement('c1', 'a1'), {
      wrapper: createWrapper(),
    });
    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(apiClient.get).toHaveBeenCalledWith(
      '/cases/c1/assets/a1/enhancements/suggest',
    );
  });
});

describe('useCreateEnhancement', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useJobStore.setState({ jobs: [] });
  });

  it('sends camel scaleFactor as snake_case scale_factor', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      workflowId: 'enhance-a1-abcd1234',
      status: 'queued',
      params: NEUTRAL_PARAMS,
    });

    const { result } = renderHook(
      () => useCreateEnhancement('c1', 'a1', 'clip.mp4'),
      { wrapper: createWrapper() },
    );
    result.current.mutate({ ...NEUTRAL_PARAMS, scaleFactor: 2 });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const [path, bodyRaw] = vi.mocked(apiClient.post).mock.calls[0];
    const body = bodyRaw as Record<string, unknown>;
    expect(path).toBe('/cases/c1/assets/a1/enhancements');
    expect(body.scale_factor).toBe(2);
    expect('scaleFactor' in body).toBe(false);
  });

  it('registers the dispatched run as an enhancement job', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      workflowId: 'enhance-a1-abcd1234',
      status: 'queued',
      params: NEUTRAL_PARAMS,
    });

    const { result } = renderHook(
      () => useCreateEnhancement('c1', 'a1', 'clip.mp4'),
      { wrapper: createWrapper() },
    );
    result.current.mutate(NEUTRAL_PARAMS);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const job = useJobStore.getState().jobs[0];
    expect(job.workflowId).toBe('enhance-a1-abcd1234');
    expect(job.kind).toBe('enhancement');
    expect(job.label).toBe('clip.mp4');
    expect(job.assetId).toBe('a1');
  });
});
