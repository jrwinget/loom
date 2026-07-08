import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useCapabilities } from '@/hooks/use-capabilities';

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

describe('useCapabilities', () => {
  beforeEach(() => {
    mockedGet.mockReset();
  });

  it('fetches the capabilities route', async () => {
    mockedGet.mockResolvedValueOnce({
      profile: 'lite',
      engines: {},
    });

    const { result } = renderHook(() => useCapabilities(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedGet).toHaveBeenCalledWith('/capabilities');
    expect(result.current.data?.profile).toBe('lite');
  });
});
