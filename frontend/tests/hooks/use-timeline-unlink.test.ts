import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { useUnlinkEvidence } from '@/hooks/use-timeline';

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
    getState: () => ({ addToast: vi.fn() }),
  },
}));

function createWrapper(): ({
  children,
}: {
  children: React.ReactNode;
}) => React.ReactElement {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return ({ children }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

describe('useUnlinkEvidence', () => {
  it('deletes the evidence link for the event', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.delete).mockResolvedValueOnce(undefined);

    const { result } = renderHook(() => useUnlinkEvidence(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({
      caseId: 'case-1',
      eventId: 'event-1',
      linkId: 'link-1',
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(vi.mocked(apiClient.delete)).toHaveBeenCalledWith(
      '/cases/case-1/events/event-1/evidence/link-1',
    );
  });

  it('reports an error when the delete fails', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.delete).mockRejectedValueOnce(
      new Error('unlink failed'),
    );

    const { result } = renderHook(() => useUnlinkEvidence(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({
      caseId: 'case-1',
      eventId: 'event-1',
      linkId: 'link-1',
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe('unlink failed');
  });
});
