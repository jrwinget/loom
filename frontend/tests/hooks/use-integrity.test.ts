import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  useDownloadIntegrityReport,
  useVerifyAsset,
  useVerifyCase,
} from '@/hooks/use-integrity';

const mockGet = vi.fn();
const mockPost = vi.fn();
vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: (path: string) => mockGet(path),
    post: (path: string) => mockPost(path),
  },
}));

const mockAddToast = vi.fn();
vi.mock('@/stores/toast-store', () => ({
  useToastStore: {
    getState: () => ({ addToast: mockAddToast }),
  },
}));

function wrapper({ children }: { children: ReactNode }): ReactNode {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return createElement(QueryClientProvider, { client: queryClient }, children);
}

describe('use-integrity', () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockAddToast.mockReset();
  });

  it('verifies one asset against the editor-gated endpoint', async () => {
    mockPost.mockResolvedValue({ assetId: 'a1', passed: true });
    const { result } = renderHook(() => useVerifyAsset('case-1'), { wrapper });

    result.current.mutate('a1');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith('/cases/case-1/assets/a1/verify');
    expect(mockAddToast).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'success' }),
    );
  });

  it('reports a failed verification as an error toast', async () => {
    mockPost.mockResolvedValue({ assetId: 'a1', passed: false });
    const { result } = renderHook(() => useVerifyAsset('case-1'), { wrapper });

    result.current.mutate('a1');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockAddToast).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error' }),
    );
  });

  it('verifies a whole case', async () => {
    mockPost.mockResolvedValue({
      caseId: 'case-1',
      totalAssets: 1,
      passedCount: 1,
      failedCount: 0,
      results: [],
    });
    const { result } = renderHook(() => useVerifyCase('case-1'), { wrapper });

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockPost).toHaveBeenCalledWith('/cases/case-1/verify');
  });

  it('fetches the report from the read-only endpoint', async () => {
    mockGet.mockResolvedValue({ assetId: 'a1', sha256Hash: 'x' });
    const createObjectURL = vi.fn(() => 'blob:report');
    const revokeObjectURL = vi.fn();
    vi.stubGlobal('URL', { createObjectURL, revokeObjectURL });
    const { result } = renderHook(
      () => useDownloadIntegrityReport('case-1'),
      { wrapper },
    );

    result.current.mutate('a1');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith(
      '/cases/case-1/assets/a1/integrity-report',
    );
    expect(createObjectURL).toHaveBeenCalled();
    vi.unstubAllGlobals();
  });

  it('toasts when the report cannot be fetched', async () => {
    mockGet.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(
      () => useDownloadIntegrityReport('case-1'),
      { wrapper },
    );

    result.current.mutate('a1');

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(mockAddToast).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'error', message: 'boom' }),
    );
  });
});
