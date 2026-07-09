import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useWorkflowStatus } from '@/hooks/use-workflow-status';

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

import { apiClient } from '@/lib/api-client';

const mockedGet = vi.mocked(apiClient.get);

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

function statusBody(status: string): Record<string, unknown> {
  return {
    workflowId: 'transcribe-1',
    status,
    stage: null,
    stepsDone: null,
    stepsTotal: null,
    error: null,
    errorCode: null,
  };
}

describe('useWorkflowStatus', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('polls the literal status route', async () => {
    mockedGet.mockResolvedValue(statusBody('running'));

    const { result } = renderHook(
      () => useWorkflowStatus('case-1', 'transcribe-1'),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedGet).toHaveBeenCalledWith(
      '/cases/case-1/workflows/transcribe-1/status',
    );
  });

  it('keeps polling while running and stops on a terminal state', async () => {
    vi.useFakeTimers();
    try {
      mockedGet
        .mockResolvedValueOnce(statusBody('running'))
        .mockResolvedValueOnce(statusBody('running'))
        .mockResolvedValue(statusBody('completed'));

      const { result } = renderHook(
        () => useWorkflowStatus('case-1', 'transcribe-1'),
        { wrapper: createWrapper() },
      );

      // three fetches: initial + two poll ticks reaching 'completed'
      await vi.waitFor(() =>
        expect(result.current.data?.status).toBe('running'),
      );
      await vi.advanceTimersByTimeAsync(1600);
      await vi.advanceTimersByTimeAsync(1600);
      await vi.waitFor(() =>
        expect(result.current.data?.status).toBe('completed'),
      );
      const callsAtCompletion = mockedGet.mock.calls.length;

      // once terminal, further time passes without new fetches
      await vi.advanceTimersByTimeAsync(10_000);
      expect(mockedGet.mock.calls.length).toBe(callsAtCompletion);
    } finally {
      vi.useRealTimers();
    }
  });

  it('does not run without a workflow id', () => {
    renderHook(() => useWorkflowStatus('case-1', ''), {
      wrapper: createWrapper(),
    });
    expect(mockedGet).not.toHaveBeenCalled();
  });
});
