import {
  QueryClient,
  QueryClientProvider,
} from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { type ReactNode, createElement } from 'react';
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest';
import { useSearch } from '@/hooks/use-search';

// mock api client
const mockGet = vi.fn();

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
  },
}));

function createWrapper(): ({
  children,
}: {
  children: ReactNode;
}) => ReactNode {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return ({ children }: { children: ReactNode }) =>
    createElement(
      QueryClientProvider,
      { client: queryClient },
      children,
    );
}

describe('useSearch', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockGet.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns empty results initially', () => {
    const { result } = renderHook(
      () => useSearch('case-1', '', []),
      { wrapper: createWrapper() },
    );

    // query disabled when query string is empty
    expect(result.current.data).toBeUndefined();
    expect(result.current.isFetching).toBe(false);
  });

  it('does not fetch when query is shorter than 2 chars', () => {
    renderHook(() => useSearch('case-1', 'a', []), {
      wrapper: createWrapper(),
    });

    // advance past debounce
    vi.advanceTimersByTime(400);

    expect(mockGet).not.toHaveBeenCalled();
  });

  it('calls API with debounced query', async () => {
    vi.useRealTimers();

    const searchResponse = {
      results: [
        {
          type: 'transcript',
          id: 'r-1',
          text: 'found it',
          assetId: 'a-1',
          relevanceScore: 0.9,
          metadata: {},
        },
      ],
      total: 1,
      facets: { transcript: 1 },
    };
    mockGet.mockResolvedValue(searchResponse);

    const { result } = renderHook(
      () => useSearch('case-1', 'test query', []),
      { wrapper: createWrapper() },
    );

    // wait for debounce (300ms) + fetch
    await waitFor(() => {
      expect(mockGet).toHaveBeenCalled();
    });

    const calledPath = mockGet.mock.calls[0][0] as string;
    expect(calledPath).toContain('/cases/case-1/search');
    expect(calledPath).toContain('q=test+query');

    await waitFor(() => {
      expect(result.current.data).toEqual(searchResponse);
    });
  });

  it('returns search results after fetch', async () => {
    vi.useRealTimers();

    const searchResponse = {
      results: [
        {
          type: 'annotation',
          id: 'r-2',
          text: 'match',
          assetId: null,
          relevanceScore: 0.8,
          metadata: {},
        },
      ],
      total: 1,
      facets: { annotation: 1 },
    };
    mockGet.mockResolvedValue(searchResponse);

    const { result } = renderHook(
      () => useSearch('case-1', 'match', ['annotation']),
      { wrapper: createWrapper() },
    );

    await waitFor(() => {
      expect(result.current.data).toEqual(searchResponse);
    });

    // verify type param was appended
    const calledPath = mockGet.mock.calls[0][0] as string;
    expect(calledPath).toContain('type=annotation');
  });

  it('handles API errors gracefully', async () => {
    vi.useRealTimers();

    mockGet.mockRejectedValue(new Error('Network error'));

    const { result } = renderHook(
      () => useSearch('case-1', 'broken query', []),
      { wrapper: createWrapper() },
    );

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.data).toBeUndefined();
  });
});
