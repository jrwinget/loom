import {
  QueryClient,
  QueryClientProvider,
} from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { type ReactNode, createElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { useIngestFromUrl } from '@/hooks/use-ingest-from-url';

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

function makeWrapper(): (props: {
  children: ReactNode;
}) => React.ReactElement {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }) =>
    createElement(QueryClientProvider, { client: qc }, children);
}

describe('useIngestFromUrl', () => {
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

    const { result } = renderHook(
      () => useIngestFromUrl('case-1'),
      { wrapper: makeWrapper() },
    );

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
      asset_id: 'asset-1',
      workflow_id: 'url-ingest-asset-1',
      status: 'queued',
    });
  });

  it('surfaces an error toast on 502', async () => {
    mockAddToast.mockReset();
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ detail: 'workflow service unavailable' }),
        { status: 502 },
      ),
    );
    vi.stubGlobal('fetch', fetchMock);

    const { result } = renderHook(
      () => useIngestFromUrl('case-1'),
      { wrapper: makeWrapper() },
    );

    result.current.mutate({ url: 'https://example.com/video.mp4' });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });
    expect(mockAddToast).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error' }),
    );
  });
});
