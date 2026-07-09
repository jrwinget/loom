import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useStartTranscription } from '@/hooks/use-transcript';
import { useStartSceneDetection } from '@/hooks/use-scenes';
import { useJobStore } from '@/stores/job-store';

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { apiClient } from '@/lib/api-client';

const mockedPost = vi.mocked(apiClient.post);

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

describe('useStartTranscription', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useJobStore.setState({ jobs: [] });
  });

  it('registers the returned workflow as a tracked job', async () => {
    mockedPost.mockResolvedValueOnce({
      workflowId: 'transcribe-asset-1',
      assetId: 'asset-1',
      status: 'queued',
    });

    const { result } = renderHook(
      () => useStartTranscription('case-1', 'asset-1', 'clip.mp4'),
      { wrapper: createWrapper() },
    );
    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedPost).toHaveBeenCalledWith(
      '/cases/case-1/assets/asset-1/transcribe',
    );

    const job = useJobStore.getState().jobs[0];
    expect(job.workflowId).toBe('transcribe-asset-1');
    expect(job.kind).toBe('transcription');
    expect(job.label).toBe('clip.mp4');
    expect(job.assetId).toBe('asset-1');
  });

  it('retry re-posts and re-registers the job as running', async () => {
    mockedPost.mockResolvedValue({
      workflowId: 'transcribe-asset-1',
      assetId: 'asset-1',
      status: 'queued',
    });

    const { result } = renderHook(
      () => useStartTranscription('case-1', 'asset-1', 'clip.mp4'),
      { wrapper: createWrapper() },
    );
    result.current.mutate();
    await waitFor(() => expect(useJobStore.getState().jobs).toHaveLength(1));

    useJobStore.getState().resolveJob('transcribe-asset-1', 'failed', 'boom');

    useJobStore.getState().jobs[0].retry?.();
    await waitFor(() =>
      expect(useJobStore.getState().jobs[0].status).toBe('running'),
    );
    expect(mockedPost).toHaveBeenCalledTimes(2);
  });
});

describe('useStartSceneDetection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useJobStore.setState({ jobs: [] });
  });

  it('registers the returned workflow as a tracked job', async () => {
    mockedPost.mockResolvedValueOnce({
      workflowId: 'scene-detect-asset-1',
      assetId: 'asset-1',
      status: 'queued',
    });

    const { result } = renderHook(
      () => useStartSceneDetection('case-1', 'asset-1', 'clip.mp4'),
      { wrapper: createWrapper() },
    );
    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedPost).toHaveBeenCalledWith(
      '/cases/case-1/assets/asset-1/scenes/detect',
    );

    const job = useJobStore.getState().jobs[0];
    expect(job.workflowId).toBe('scene-detect-asset-1');
    expect(job.kind).toBe('scene_detection');
  });
});
