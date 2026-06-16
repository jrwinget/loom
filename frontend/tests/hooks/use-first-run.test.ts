import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook } from '@testing-library/react';
import { createElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  firstRunKeys,
  useCompleteFirstRun,
  type FirstRunStatus,
} from '@/hooks/use-first-run';

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('@/stores/auth-store', () => ({
  useAuthStore: {
    getState: () => ({ token: 'test-token' }),
  },
}));

function setup(): {
  queryClient: QueryClient;
  wrapper: ({ children }: { children: React.ReactNode }) => React.ReactElement;
} {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const wrapper = ({
    children,
  }: {
    children: React.ReactNode;
  }): React.ReactElement =>
    createElement(QueryClientProvider, { client: queryClient }, children);
  return { queryClient, wrapper };
}

const completeResponse = {
  user_id: 'u1',
  access_token: 'tok',
  refresh_token: 'ref',
  password_recovery_codes: ['a-b-c-d-e'],
};

describe('useCompleteFirstRun', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('flips cached first-run status to not-required, preserving other fields', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.post).mockResolvedValueOnce(completeResponse);

    const { queryClient, wrapper } = setup();
    queryClient.setQueryData<FirstRunStatus>(firstRunKeys.status, {
      first_run_required: true,
      deployment_profile: 'lite',
      data_dir: '/case-files',
    });

    const { result } = renderHook(() => useCompleteFirstRun(), { wrapper });
    await result.current.mutateAsync({
      admin_email: 'admin@example.com',
      admin_password: 'supersecret-123',
      admin_full_name: 'Admin',
    });

    expect(
      queryClient.getQueryData<FirstRunStatus>(firstRunKeys.status),
    ).toEqual({
      first_run_required: false,
      deployment_profile: 'lite',
      data_dir: '/case-files',
    });
  });

  it('marks first-run complete even with no prior cached status', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.post).mockResolvedValueOnce(completeResponse);

    const { queryClient, wrapper } = setup();
    const { result } = renderHook(() => useCompleteFirstRun(), { wrapper });
    await result.current.mutateAsync({
      admin_email: 'admin@example.com',
      admin_password: 'supersecret-123',
      admin_full_name: 'Admin',
    });

    expect(
      queryClient.getQueryData<FirstRunStatus>(firstRunKeys.status)
        ?.first_run_required,
    ).toBe(false);
  });
});
