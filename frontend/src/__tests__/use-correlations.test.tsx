/// <reference types="@testing-library/jest-dom" />
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  useCorrelationCandidates,
  useDecideCorrelation,
  useScanCorrelations,
} from '@/hooks/use-correlations';

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { apiClient } from '@/lib/api-client';

const mockedGet = vi.mocked(apiClient.get);
const mockedPost = vi.mocked(apiClient.post);

function createWrapper(): React.FC<{ children: React.ReactNode }> {
  const queryClient = new QueryClient({
    defaultOptions: {
      mutations: { retry: false },
      queries: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return createElement(QueryClientProvider, {
      client: queryClient,
      children,
    });
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useCorrelationCandidates', () => {
  it('queries the case correlation list with no status filter', async () => {
    mockedGet.mockResolvedValueOnce({ candidates: [], total: 0 });
    const { result } = renderHook(() => useCorrelationCandidates('case-1'), {
      wrapper: createWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedGet).toHaveBeenCalledWith('/cases/case-1/correlations');
  });

  it('appends ?status when provided', async () => {
    mockedGet.mockResolvedValueOnce({ candidates: [], total: 0 });
    renderHook(() => useCorrelationCandidates('case-1', 'pending'), {
      wrapper: createWrapper(),
    });
    await waitFor(() =>
      expect(mockedGet).toHaveBeenCalledWith(
        '/cases/case-1/correlations?status=pending',
      ),
    );
  });

  it('does not run without a caseId', () => {
    renderHook(() => useCorrelationCandidates(''), {
      wrapper: createWrapper(),
    });
    expect(mockedGet).not.toHaveBeenCalled();
  });
});

describe('useScanCorrelations', () => {
  it('posts to the scan endpoint', async () => {
    mockedPost.mockResolvedValueOnce({ candidates: [], total: 0 });
    const { result } = renderHook(() => useScanCorrelations('case-1'), {
      wrapper: createWrapper(),
    });
    result.current.mutate();
    await waitFor(() =>
      expect(mockedPost).toHaveBeenCalledWith(
        '/cases/case-1/correlations/scan',
      ),
    );
  });
});

describe('useDecideCorrelation', () => {
  it('posts the decision payload to the decide endpoint', async () => {
    mockedPost.mockResolvedValueOnce({ id: 'cand-1' });
    const { result } = renderHook(() => useDecideCorrelation('case-1'), {
      wrapper: createWrapper(),
    });
    result.current.mutate({
      candidateId: 'cand-1',
      payload: { status: 'accepted' },
    });
    await waitFor(() =>
      expect(mockedPost).toHaveBeenCalledWith(
        '/cases/case-1/correlations/cand-1/decide',
        { status: 'accepted' },
      ),
    );
  });

  it('handles rejection symmetrically', async () => {
    mockedPost.mockResolvedValueOnce({ id: 'cand-2' });
    const { result } = renderHook(() => useDecideCorrelation('case-1'), {
      wrapper: createWrapper(),
    });
    result.current.mutate({
      candidateId: 'cand-2',
      payload: { status: 'rejected' },
    });
    await waitFor(() =>
      expect(mockedPost).toHaveBeenCalledWith(
        '/cases/case-1/correlations/cand-2/decide',
        { status: 'rejected' },
      ),
    );
  });
});
