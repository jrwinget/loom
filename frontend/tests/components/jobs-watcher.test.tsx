/// <reference types="@testing-library/jest-dom" />
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { JobsWatcher } from '@/components/layout/jobs-watcher';
import { queryKeys } from '@/lib/query-keys';
import { useJobStore } from '@/stores/job-store';

const { addToast } = vi.hoisted(() => ({ addToast: vi.fn() }));

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

vi.mock('@/stores/toast-store', () => ({
  useToastStore: {
    getState: () => ({ addToast }),
  },
}));

import { apiClient } from '@/lib/api-client';

const mockedGet = vi.mocked(apiClient.get);

function statusBody(
  status: string,
  over: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    workflowId: 'transcribe-1',
    status,
    stage: null,
    stepsDone: null,
    stepsTotal: null,
    error: null,
    errorCode: null,
    ...over,
  };
}

function renderWatcher(): QueryClient {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <JobsWatcher />
    </QueryClientProvider>,
  );
  return queryClient;
}

describe('JobsWatcher', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useJobStore.setState({ jobs: [] });
  });

  it('resolves a completed job, toasts, and refreshes its queries', async () => {
    mockedGet.mockResolvedValue(statusBody('completed'));
    useJobStore.getState().registerJob({
      workflowId: 'transcribe-1',
      caseId: 'case-1',
      kind: 'transcription',
      label: 'clip.mp4',
      assetId: 'asset-1',
    });

    const queryClient = renderWatcher();
    const invalidate = vi.spyOn(queryClient, 'invalidateQueries');

    await waitFor(() =>
      expect(useJobStore.getState().jobs[0].status).toBe('completed'),
    );
    expect(addToast).toHaveBeenCalledWith({
      type: 'success',
      message: 'clip.mp4 finished',
    });
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.transcripts.byAsset('case-1', 'asset-1'),
    });
  });

  it('surfaces the backend error on failure', async () => {
    mockedGet.mockResolvedValue(
      statusBody('failed', {
        error: 'install the ai extra',
        errorCode: 'engine_unavailable',
      }),
    );
    useJobStore.getState().registerJob({
      workflowId: 'transcribe-1',
      caseId: 'case-1',
      kind: 'transcription',
      label: 'clip.mp4',
      assetId: 'asset-1',
    });

    renderWatcher();

    await waitFor(() =>
      expect(useJobStore.getState().jobs[0].status).toBe('failed'),
    );
    const job = useJobStore.getState().jobs[0];
    expect(job.error).toBe('install the ai extra');
    expect(job.errorCode).toBe('engine_unavailable');
    expect(addToast).toHaveBeenCalledWith({
      type: 'error',
      message: 'clip.mp4 failed: install the ai extra',
    });
  });

  it('records lite stage progress while running', async () => {
    mockedGet.mockResolvedValue(
      statusBody('running', {
        stage: 'store_transcript',
        stepsDone: 2,
        stepsTotal: 3,
      }),
    );
    useJobStore.getState().registerJob({
      workflowId: 'transcribe-1',
      caseId: 'case-1',
      kind: 'transcription',
      label: 'clip.mp4',
    });

    renderWatcher();

    await waitFor(() =>
      expect(useJobStore.getState().jobs[0].stage).toBe('store_transcript'),
    );
    expect(useJobStore.getState().jobs[0].stepsDone).toBe(2);
  });

  it('marks the job failed when the status fetch errors', async () => {
    mockedGet.mockRejectedValue(new Error('404'));
    useJobStore.getState().registerJob({
      workflowId: 'gone-1',
      caseId: 'case-1',
      kind: 'export',
      label: 'Court bundle',
    });

    renderWatcher();

    await waitFor(() =>
      expect(useJobStore.getState().jobs[0].status).toBe('failed'),
    );
    expect(addToast).toHaveBeenCalledWith({
      type: 'error',
      message: 'Court bundle: could not fetch job status',
    });
  });
});
