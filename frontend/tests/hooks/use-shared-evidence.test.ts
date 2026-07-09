import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  useIncomingShared,
  useOutgoingShared,
  useShareEvidence,
  useRevokeShare,
} from '@/hooks/use-shared-evidence';
import type { SharedEvidence } from '@/types/organization';

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

const link: SharedEvidence = {
  id: 'link-1',
  sourceCaseId: 'case-1',
  targetCaseId: 'case-2',
  assetId: 'asset-1',
  originalFilename: 'clip.mp4',
  sharedBy: 'user-1',
  accessLevel: 'view',
  expiresAt: null,
  createdAt: '2026-01-01T00:00:00Z',
};

function createWrapper(): ({
  children,
}: {
  children: React.ReactNode;
}) => React.ReactElement {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return ({ children }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useIncomingShared', () => {
  it('fetches incoming shared evidence for a case', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.get).mockResolvedValueOnce([link]);

    const { result } = renderHook(() => useIncomingShared('case-2'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(vi.mocked(apiClient.get)).toHaveBeenCalledWith(
      '/cases/case-2/shared-evidence/incoming',
    );
  });

  it('is disabled when caseId is empty', () => {
    const { result } = renderHook(() => useIncomingShared(''), {
      wrapper: createWrapper(),
    });

    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('useOutgoingShared', () => {
  it('fetches outgoing shared evidence for a case', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.get).mockResolvedValueOnce([link]);

    const { result } = renderHook(() => useOutgoingShared('case-1'), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(vi.mocked(apiClient.get)).toHaveBeenCalledWith(
      '/cases/case-1/shared-evidence/outgoing',
    );
  });
});

describe('useShareEvidence', () => {
  it('maps the share fields to a snake_case body and defaults access to view', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.post).mockResolvedValueOnce(link);

    const { result } = renderHook(() => useShareEvidence(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({
      caseId: 'case-1',
      targetCaseId: 'case-2',
      assetId: 'asset-1',
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(vi.mocked(apiClient.post)).toHaveBeenCalledWith(
      '/cases/case-1/shared-evidence',
      {
        target_case_id: 'case-2',
        asset_id: 'asset-1',
        access_level: 'view',
        expires_at: undefined,
      },
    );
  });

  it('passes through an explicit access level', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.post).mockResolvedValueOnce(link);

    const { result } = renderHook(() => useShareEvidence(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({
      caseId: 'case-1',
      targetCaseId: 'case-2',
      assetId: 'asset-1',
      accessLevel: 'edit',
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(vi.mocked(apiClient.post)).toHaveBeenCalledWith(
      '/cases/case-1/shared-evidence',
      expect.objectContaining({ access_level: 'edit' }),
    );
  });
});

describe('useRevokeShare', () => {
  it('deletes the share link by id', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.delete).mockResolvedValueOnce(undefined);

    const { result } = renderHook(() => useRevokeShare(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({ caseId: 'case-1', linkId: 'link-1' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(vi.mocked(apiClient.delete)).toHaveBeenCalledWith(
      '/cases/case-1/shared-evidence/link-1',
    );
  });
});
