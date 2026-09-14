import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  useApproveNarrative,
  useGenerateNarrative,
  useNarratives,
  useRejectNarrative,
} from '@/hooks/use-narratives';

const mockGet = vi.fn();
const mockPost = vi.fn();
vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: (path: string) => mockGet(path),
    post: (path: string, body?: unknown) => mockPost(path, body),
  },
}));

const mockAddToast = vi.fn();
vi.mock('@/stores/toast-store', () => ({
  useToastStore: {
    getState: () => ({ addToast: mockAddToast }),
  },
}));

function wrapper({ children }: { children: ReactNode }): ReactNode {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return createElement(QueryClientProvider, { client: queryClient }, children);
}

describe('use-narratives', () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockAddToast.mockReset();
  });

  it('lists narratives for a case', async () => {
    mockGet.mockResolvedValue({ items: [{ id: 'n1' }] });
    const { result } = renderHook(() => useNarratives('case-1'), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith('/cases/case-1/narratives');
    expect(result.current.data).toEqual([{ id: 'n1' }]);
  });

  it('scopes the list to an asset when given', async () => {
    mockGet.mockResolvedValue({ items: [] });
    const { result } = renderHook(() => useNarratives('case-1', 'asset-9'), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith(
      '/cases/case-1/narratives?asset_id=asset-9',
    );
  });

  it('generates a case-wide narrative with a null asset_id', async () => {
    mockPost.mockResolvedValue({ id: 'n1', status: 'draft' });
    const { result } = renderHook(() => useGenerateNarrative('case-1'), {
      wrapper,
    });

    result.current.mutate(undefined);

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith('/cases/case-1/narratives', {
      asset_id: null,
    });
  });

  it('generates an asset-scoped narrative', async () => {
    mockPost.mockResolvedValue({ id: 'n1', status: 'draft' });
    const { result } = renderHook(() => useGenerateNarrative('case-1'), {
      wrapper,
    });

    result.current.mutate('asset-9');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith('/cases/case-1/narratives', {
      asset_id: 'asset-9',
    });
  });

  it('toasts when generation fails', async () => {
    mockPost.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useGenerateNarrative('case-1'), {
      wrapper,
    });

    result.current.mutate(undefined);

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(mockAddToast).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', message: 'boom' }),
    );
  });

  it('approves a narrative via the dedicated endpoint', async () => {
    mockPost.mockResolvedValue({ id: 'n1', status: 'approved' });
    const { result } = renderHook(() => useApproveNarrative('case-1'), {
      wrapper,
    });

    result.current.mutate('n1');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith(
      '/cases/case-1/narratives/n1/approve',
      undefined,
    );
  });

  it('rejects a narrative via the dedicated endpoint', async () => {
    mockPost.mockResolvedValue({ id: 'n1', status: 'rejected' });
    const { result } = renderHook(() => useRejectNarrative('case-1'), {
      wrapper,
    });

    result.current.mutate('n1');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith(
      '/cases/case-1/narratives/n1/reject',
      undefined,
    );
  });
});
