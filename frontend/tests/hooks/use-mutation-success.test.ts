import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  useProposeClusters,
  useAcceptCluster,
  useRejectCluster,
  useMergeClusters,
} from '@/hooks/use-clusters';
import {
  useCreateResolution,
  useUpdateResolution,
} from '@/hooks/use-conflicts';
import {
  useCreatePlugin,
  useUpdatePlugin,
  useDeletePlugin,
  useCreateWebhook,
} from '@/hooks/use-plugins';
import { useCreateOrg } from '@/hooks/use-organizations';
import { useToastStore } from '@/stores/toast-store';

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn().mockResolvedValue({}),
    post: vi.fn().mockResolvedValue({}),
    patch: vi.fn().mockResolvedValue({}),
    delete: vi.fn().mockResolvedValue(undefined),
  },
}));

function createWrapper(): React.FC<{ children: React.ReactNode }> {
  const queryClient = new QueryClient({
    defaultOptions: {
      mutations: { retry: false },
      queries: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return createElement(QueryClientProvider, {
      client: queryClient,
      children,
    });
  };
}

describe('mutation onSuccess toasts', () => {
  beforeEach(() => {
    useToastStore.setState({ toasts: [] });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('useProposeClusters shows success toast', async () => {
    const { result } = renderHook(() => useProposeClusters('c1'), {
      wrapper: createWrapper(),
    });
    result.current.mutate({ window_seconds: 3600 });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(useToastStore.getState().toasts).toMatchObject([
      { type: 'success', message: 'Clusters proposed' },
    ]);
  });

  it('useAcceptCluster shows success toast', async () => {
    const { result } = renderHook(() => useAcceptCluster('c1'), {
      wrapper: createWrapper(),
    });
    result.current.mutate({ clusterId: 'cl1', payload: { title: 'x' } });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(useToastStore.getState().toasts).toMatchObject([
      { type: 'success', message: 'Cluster accepted' },
    ]);
  });

  it('useRejectCluster shows success toast', async () => {
    const { result } = renderHook(() => useRejectCluster('c1'), {
      wrapper: createWrapper(),
    });
    result.current.mutate('cl1');
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(useToastStore.getState().toasts).toMatchObject([
      { type: 'success', message: 'Cluster rejected' },
    ]);
  });

  it('useMergeClusters shows success toast', async () => {
    const { result } = renderHook(() => useMergeClusters('c1'), {
      wrapper: createWrapper(),
    });
    result.current.mutate(['a', 'b']);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(useToastStore.getState().toasts).toMatchObject([
      { type: 'success', message: 'Clusters merged' },
    ]);
  });

  it('useCreateResolution shows success toast', async () => {
    const { result } = renderHook(
      () => useCreateResolution('c1', 'e1'),
      { wrapper: createWrapper() },
    );
    result.current.mutate({ resolution: 'accept_a', notes: '' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(useToastStore.getState().toasts).toMatchObject([
      { type: 'success', message: 'Resolution recorded' },
    ]);
  });

  it('useUpdateResolution shows success toast', async () => {
    const { result } = renderHook(() => useUpdateResolution('c1'), {
      wrapper: createWrapper(),
    });
    result.current.mutate({
      eventId: 'e1',
      resolutionId: 'r1',
      payload: { resolution: 'accept_a', notes: '' },
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(useToastStore.getState().toasts).toMatchObject([
      { type: 'success', message: 'Resolution updated' },
    ]);
  });

  it('useCreatePlugin shows success toast', async () => {
    const { result } = renderHook(() => useCreatePlugin(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({ name: 'p', description: '' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(useToastStore.getState().toasts).toMatchObject([
      { type: 'success', message: 'Plugin created' },
    ]);
  });

  it('useUpdatePlugin shows success toast', async () => {
    const { result } = renderHook(() => useUpdatePlugin('p1'), {
      wrapper: createWrapper(),
    });
    result.current.mutate({ name: 'p2' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(useToastStore.getState().toasts).toMatchObject([
      { type: 'success', message: 'Plugin updated' },
    ]);
  });

  it('useDeletePlugin shows success toast', async () => {
    const { result } = renderHook(() => useDeletePlugin(), {
      wrapper: createWrapper(),
    });
    result.current.mutate('p1');
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(useToastStore.getState().toasts).toMatchObject([
      { type: 'success', message: 'Plugin deleted' },
    ]);
  });

  it('useCreateWebhook shows success toast', async () => {
    const { result } = renderHook(() => useCreateWebhook('p1'), {
      wrapper: createWrapper(),
    });
    result.current.mutate({ url: 'https://x', events: [] });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(useToastStore.getState().toasts).toMatchObject([
      { type: 'success', message: 'Webhook created' },
    ]);
  });

  it('useCreateOrg shows success toast', async () => {
    const { result } = renderHook(() => useCreateOrg(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({ name: 'org' });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(useToastStore.getState().toasts).toMatchObject([
      { type: 'success', message: 'Organization created' },
    ]);
  });
});
