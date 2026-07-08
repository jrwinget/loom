import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useCreateExport, useDownloadExport } from '@/hooks/use-exports';
import { useJobStore } from '@/stores/job-store';

const { addToast, triggerDownload } = vi.hoisted(() => ({
  addToast: vi.fn(),
  triggerDownload: vi.fn(),
}));

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('@/lib/utils', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  triggerDownload,
}));

vi.mock('@/stores/toast-store', () => ({
  useToastStore: {
    getState: () => ({ addToast }),
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

describe('useCreateExport', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useJobStore.setState({ jobs: [] });
  });

  it('tracks the deterministic export workflow as a job', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.post).mockResolvedValueOnce({
      id: 'exp-1',
      name: 'Court bundle',
      status: 'pending',
    });

    const { result } = renderHook(() => useCreateExport('case-1'), {
      wrapper: createWrapper(),
    });
    result.current.mutate({ name: 'Court bundle', format: 'court_bundle' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const job = useJobStore.getState().jobs[0];
    expect(job.workflowId).toBe('export-exp-1');
    expect(job.kind).toBe('export');
    expect(job.label).toBe('Court bundle');
  });
});

describe('useDownloadExport', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('fetches export detail and opens the download url', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      id: 'exp-1',
      status: 'complete',
      downloadUrl: 'https://storage.example/exports/e.zip?sig=abc',
    });

    const { result } = renderHook(() => useDownloadExport('case-1'), {
      wrapper: createWrapper(),
    });
    result.current.mutate('exp-1');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(apiClient.get).toHaveBeenCalledWith('/cases/case-1/exports/exp-1');
    expect(triggerDownload).toHaveBeenCalledWith(
      'https://storage.example/exports/e.zip?sig=abc',
    );
  });

  it('toasts an error when the download url is not ready', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      id: 'exp-1',
      status: 'complete',
      downloadUrl: null,
    });

    const { result } = renderHook(() => useDownloadExport('case-1'), {
      wrapper: createWrapper(),
    });
    result.current.mutate('exp-1');

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(triggerDownload).not.toHaveBeenCalled();
    expect(addToast).toHaveBeenCalledWith({
      type: 'error',
      message: 'Download is not ready yet',
    });
  });

  it('toasts the error message when the request fails', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.get).mockRejectedValueOnce(
      new Error('export not found'),
    );

    const { result } = renderHook(() => useDownloadExport('case-1'), {
      wrapper: createWrapper(),
    });
    result.current.mutate('exp-1');

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(triggerDownload).not.toHaveBeenCalled();
    expect(addToast).toHaveBeenCalledWith({
      type: 'error',
      message: 'export not found',
    });
  });
});
