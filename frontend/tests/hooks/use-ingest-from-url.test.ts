import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { type ReactNode, createElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useIngestFromUrl } from '@/hooks/use-ingest-from-url';
import { useJobStore } from '@/stores/job-store';

vi.mock('@/stores/auth-store', () => ({
  useAuthStore: {
    getState: () => ({ token: 'test-token' }),
  },
}));

const mockAddToast = vi.fn();
vi.mock('@/stores/toast-store', () => ({
  useToastStore: {
    getState: () => ({ addToast: mockAddToast }),
  },
}));

function makeWrapper(): (props: { children: ReactNode }) => React.ReactElement {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }) =>
    createElement(QueryClientProvider, { client: qc }, children);
}

describe('useIngestFromUrl', () => {
  beforeEach(() => {
    useJobStore.setState({ jobs: [] });
  });

  it('POSTs to the expected endpoint and returns response', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          asset_id: 'asset-1',
          workflow_id: 'url-ingest-asset-1',
          status: 'queued',
        }),
        { status: 201 },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useIngestFromUrl('case-1'), {
      wrapper: makeWrapper(),
    });

    result.current.mutate({ url: 'https://example.com/video.mp4' });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/cases/case-1/assets/ingest-url',
      expect.objectContaining({
        method: 'POST',
      }),
    );
    expect(result.current.data).toEqual({
      assetId: 'asset-1',
      workflowId: 'url-ingest-asset-1',
      status: 'queued',
    });

    // the ingest shows up in the jobs menu, labeled by its url
    const job = useJobStore.getState().jobs[0];
    expect(job.workflowId).toBe('url-ingest-asset-1');
    expect(job.kind).toBe('url_ingest');
    expect(job.label).toBe('https://example.com/video.mp4');
  });

  it('surfaces an error toast on 502', async () => {
    mockAddToast.mockReset();
    const fetchMock = vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ detail: 'workflow service unavailable' }),
          { status: 502 },
        ),
      );
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(() => useIngestFromUrl('case-1'), {
      wrapper: makeWrapper(),
    });

    result.current.mutate({ url: 'https://example.com/video.mp4' });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(mockAddToast).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error' }),
    );
  });
});
