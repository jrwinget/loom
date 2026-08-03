import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useReleaseHold, useSetHold } from '@/hooks/use-case-hold';
import { queryKeys } from '@/lib/query-keys';

const { addToast } = vi.hoisted(() => ({
  addToast: vi.fn(),
}));

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('@/stores/toast-store', () => ({
  useToastStore: {
    getState: () => ({ addToast }),
  },
}));

import { apiClient } from '@/lib/api-client';

const mockedPost = vi.mocked(apiClient.post);

function createWrapper(queryClient: QueryClient): ({
  children,
}: {
  children: React.ReactNode;
}) => React.ReactElement {
  return ({ children }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

function makeClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useSetHold', () => {
  it('posts the reason to the hold endpoint', async () => {
    mockedPost.mockResolvedValueOnce({ holdActive: true } as never);
    const { result } = renderHook(() => useSetHold('c1'), {
      wrapper: createWrapper(makeClient()),
    });

    result.current.mutate('pending litigation');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedPost).toHaveBeenCalledWith('/cases/c1/hold', {
      reason: 'pending litigation',
    });
    expect(addToast).toHaveBeenCalledWith({
      type: 'success',
      message: 'Litigation hold set',
    });
  });

  it('invalidates the case queries on success', async () => {
    mockedPost.mockResolvedValueOnce({ holdActive: true } as never);
    const queryClient = makeClient();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    const { result } = renderHook(() => useSetHold('c1'), {
      wrapper: createWrapper(queryClient),
    });

    result.current.mutate('pending litigation');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.cases.detail('c1'),
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.cases.all,
    });
  });

  it('surfaces an error toast when the request fails', async () => {
    mockedPost.mockRejectedValueOnce(new Error('case is already held'));
    const { result } = renderHook(() => useSetHold('c1'), {
      wrapper: createWrapper(makeClient()),
    });

    result.current.mutate('pending litigation');

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(addToast).toHaveBeenCalledWith({
      type: 'error',
      message: 'case is already held',
    });
  });
});

describe('useReleaseHold', () => {
  it('posts the reason to the release endpoint', async () => {
    mockedPost.mockResolvedValueOnce({ holdActive: false } as never);
    const { result } = renderHook(() => useReleaseHold('c1'), {
      wrapper: createWrapper(makeClient()),
    });

    result.current.mutate('matter settled');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedPost).toHaveBeenCalledWith('/cases/c1/hold/release', {
      reason: 'matter settled',
    });
    expect(addToast).toHaveBeenCalledWith({
      type: 'success',
      message: 'Litigation hold released',
    });
  });

  it('invalidates the case queries on success', async () => {
    mockedPost.mockResolvedValueOnce({ holdActive: false } as never);
    const queryClient = makeClient();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');
    const { result } = renderHook(() => useReleaseHold('c1'), {
      wrapper: createWrapper(queryClient),
    });

    result.current.mutate('matter settled');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.cases.detail('c1'),
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.cases.all,
    });
  });

  it('surfaces an error toast when the request fails', async () => {
    mockedPost.mockRejectedValueOnce(new Error('case is not held'));
    const { result } = renderHook(() => useReleaseHold('c1'), {
      wrapper: createWrapper(makeClient()),
    });

    result.current.mutate('matter settled');

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(addToast).toHaveBeenCalledWith({
      type: 'error',
      message: 'case is not held',
    });
  });
});
