/// <reference types="@testing-library/jest-dom" />
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// these tests guard the frontend<->backend route contract that broke
// in v0.1.13: uploads must POST to /assets/upload (not /assets), and
// the asset detail must be case-scoped (not /assets/:id). a drift
// here is exactly the "Upload all -> Error" / 404 bug class.

vi.mock('@/lib/api-client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
  getApiOrigin: () => 'http://api.test',
}));

vi.mock('@/stores/auth-store', () => ({
  useAuthStore: { getState: () => ({ token: 'test-token' }) },
}));

import { apiClient } from '@/lib/api-client';
import { useAsset } from '@/hooks/use-assets';
import { useUpload, useUploadStore } from '@/hooks/use-upload';

const mockedGet = vi.mocked(apiClient.get);

const openCalls: Array<[string, string]> = [];

class MockXHR {
  status = 201;
  statusText = 'Created';
  responseText = '{}';
  upload = { addEventListener: vi.fn() };
  private handlers: Record<string, () => void> = {};

  open(method: string, url: string): void {
    openCalls.push([method, url]);
  }

  setRequestHeader(): void {}

  addEventListener(event: string, cb: () => void): void {
    this.handlers[event] = cb;
  }

  send(): void {
    this.handlers.load?.();
  }
}

function createWrapper(): React.FC<{ children: React.ReactNode }> {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return createElement(QueryClientProvider, {
      client: queryClient,
      children,
    });
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  openCalls.length = 0;
  useUploadStore.getState().clear();
  vi.stubGlobal('XMLHttpRequest', MockXHR);
});

describe('useAsset', () => {
  it('fetches the case-scoped asset detail route', async () => {
    mockedGet.mockResolvedValueOnce({ id: 'asset-1' });
    renderHook(() => useAsset('case-1', 'asset-1'), {
      wrapper: createWrapper(),
    });
    await waitFor(() =>
      expect(mockedGet).toHaveBeenCalledWith('/cases/case-1/assets/asset-1'),
    );
  });

  it('does not run without a caseId', () => {
    renderHook(() => useAsset('', 'asset-1'), { wrapper: createWrapper() });
    expect(mockedGet).not.toHaveBeenCalled();
  });
});

describe('useUpload', () => {
  it('uploads to the /assets/upload route', async () => {
    const { result } = renderHook(() => useUpload());

    const file = new File([new Uint8Array([1, 2, 3])], 'evidence.pdf', {
      type: 'application/pdf',
    });

    act(() => {
      result.current.addFiles([file]);
    });

    await act(async () => {
      await result.current.uploadAll('case-1');
    });

    expect(openCalls).toContainEqual([
      'POST',
      'http://api.test/cases/case-1/assets/upload',
    ]);
  });
});
