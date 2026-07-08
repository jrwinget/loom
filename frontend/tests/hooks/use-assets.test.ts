import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useAssets, useAsset, useAssetDownloadUrl } from '@/hooks/use-assets';
import type { Asset, AssetListResponse } from '@/types/asset';

const mockAsset: Asset = {
  id: 'asset-1',
  caseId: 'case-1',
  originalFilename: 'protest.mp4',
  storageKey: 'originals/abc.mp4',
  mediaType: 'video',
  mimeType: 'video/mp4',
  fileSizeBytes: 1024000,
  sha256Hash: 'abc123',
  uploadStatus: 'complete',
  processingStatus: 'complete',
  captureTime: '2026-01-15T10:00:00Z',
  createdAt: '2026-01-15T10:00:00Z',
  updatedAt: '2026-01-15T10:00:00Z',
};

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

vi.mock('@/stores/toast-store', () => ({
  useToastStore: {
    getState: () => ({ addToast: vi.fn() }),
  },
}));

function createWrapper(): ({ children }: { children: React.ReactNode }) => React.ReactElement {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return ({ children }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

describe('useAssets', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches assets for a case', async () => {
    const { apiClient } = await import('@/lib/api-client');
    const response: AssetListResponse = {
      items: [mockAsset],
      total: 1,
    };
    vi.mocked(apiClient.get).mockResolvedValueOnce(response);

    const { result } = renderHook(
      () => useAssets('case-1'),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([mockAsset]);
  });

  it('is disabled when caseId is empty', () => {
    const { result } = renderHook(
      () => useAssets(''),
      { wrapper: createWrapper() },
    );

    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('useAsset', () => {
  it('fetches a single asset', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.get).mockResolvedValueOnce(mockAsset);

    const { result } = renderHook(
      () => useAsset('case-1', 'asset-1'),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockAsset);
    expect(vi.mocked(apiClient.get)).toHaveBeenCalledWith(
      '/cases/case-1/assets/asset-1',
    );
  });

  it('is disabled when assetId is empty', () => {
    const { result } = renderHook(
      () => useAsset('case-1', ''),
      { wrapper: createWrapper() },
    );

    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('useAssetDownloadUrl', () => {
  it('fetches download url', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      url: 'https://minio.local/presigned',
    });

    const { result } = renderHook(
      () => useAssetDownloadUrl('case-1', 'asset-1'),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBe('https://minio.local/presigned');
  });

  it('is disabled when ids are empty', () => {
    const { result } = renderHook(
      () => useAssetDownloadUrl('', ''),
      { wrapper: createWrapper() },
    );

    expect(result.current.fetchStatus).toBe('idle');
  });
});
