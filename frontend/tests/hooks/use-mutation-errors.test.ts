import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useProposeClusters, useAcceptCluster, useRejectCluster, useMergeClusters } from '@/hooks/use-clusters';
import { useCreateResolution, useUpdateResolution } from '@/hooks/use-conflicts';
import { useCreatePlugin, useUpdatePlugin, useDeletePlugin, useCreateWebhook } from '@/hooks/use-plugins';
import { useCreateOrg } from '@/hooks/use-organizations';
import { useToastStore } from '@/stores/toast-store';

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn().mockRejectedValue(new Error('fail')),
    post: vi.fn().mockRejectedValue(new Error('fail')),
    patch: vi.fn().mockRejectedValue(new Error('fail')),
    delete: vi.fn().mockRejectedValue(new Error('fail')),
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

describe('mutation onError toasts', () => {
  beforeEach(() => {
    useToastStore.setState({ toasts: [] });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('useProposeClusters shows error toast', async () => {
    const { result } = renderHook(
      () => useProposeClusters('c1'),
      { wrapper: createWrapper() },
    );
    result.current.mutate({ window_seconds: 3600 });
    await waitFor(() => expect(result.current.isError).toBe(true));
    const toasts = useToastStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0]).toMatchObject({
      type: 'error',
      message: 'Failed to propose clusters',
    });
  });

  it('useAcceptCluster shows error toast', async () => {
    const { result } = renderHook(
      () => useAcceptCluster('c1'),
      { wrapper: createWrapper() },
    );
    result.current.mutate({ clusterId: 'cl1', payload: { title: 'x' } });
    await waitFor(() => expect(result.current.isError).toBe(true));
    const toasts = useToastStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0]).toMatchObject({
      type: 'error',
      message: 'Failed to accept cluster',
    });
  });

  it('useRejectCluster shows error toast', async () => {
    const { result } = renderHook(
      () => useRejectCluster('c1'),
      { wrapper: createWrapper() },
    );
    result.current.mutate('cl1');
    await waitFor(() => expect(result.current.isError).toBe(true));
    const toasts = useToastStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0]).toMatchObject({
      type: 'error',
      message: 'Failed to reject cluster',
    });
  });

  it('useMergeClusters shows error toast', async () => {
    const { result } = renderHook(
      () => useMergeClusters('c1'),
      { wrapper: createWrapper() },
    );
    result.current.mutate(['cl1', 'cl2']);
    await waitFor(() => expect(result.current.isError).toBe(true));
    const toasts = useToastStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0]).toMatchObject({
      type: 'error',
      message: 'Failed to merge clusters',
    });
  });

  it('useCreateResolution shows error toast', async () => {
    const { result } = renderHook(
      () => useCreateResolution('c1', 'e1'),
      { wrapper: createWrapper() },
    );
    result.current.mutate({
      resolutionType: 'accept_a',
      notes: 'test',
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    const toasts = useToastStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0]).toMatchObject({
      type: 'error',
      message: 'Failed to create resolution',
    });
  });

  it('useUpdateResolution shows error toast', async () => {
    const { result } = renderHook(
      () => useUpdateResolution('c1'),
      { wrapper: createWrapper() },
    );
    result.current.mutate({
      eventId: 'e1',
      resolutionId: 'r1',
      payload: { resolutionType: 'accept_b', notes: 'x' },
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    const toasts = useToastStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0]).toMatchObject({
      type: 'error',
      message: 'Failed to update resolution',
    });
  });

  it('useCreatePlugin shows error toast', async () => {
    const { result } = renderHook(
      () => useCreatePlugin(),
      { wrapper: createWrapper() },
    );
    result.current.mutate({
      name: 'test',
      version: '1.0',
      plugin_type: 'webhook',
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    const toasts = useToastStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0]).toMatchObject({
      type: 'error',
      message: 'Failed to create plugin',
    });
  });

  it('useUpdatePlugin shows error toast', async () => {
    const { result } = renderHook(
      () => useUpdatePlugin('p1'),
      { wrapper: createWrapper() },
    );
    result.current.mutate({ description: 'updated' });
    await waitFor(() => expect(result.current.isError).toBe(true));
    const toasts = useToastStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0]).toMatchObject({
      type: 'error',
      message: 'Failed to update plugin',
    });
  });

  it('useDeletePlugin shows error toast', async () => {
    const { result } = renderHook(
      () => useDeletePlugin(),
      { wrapper: createWrapper() },
    );
    result.current.mutate('p1');
    await waitFor(() => expect(result.current.isError).toBe(true));
    const toasts = useToastStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0]).toMatchObject({
      type: 'error',
      message: 'Failed to delete plugin',
    });
  });

  it('useCreateWebhook shows error toast', async () => {
    const { result } = renderHook(
      () => useCreateWebhook('p1'),
      { wrapper: createWrapper() },
    );
    result.current.mutate({
      plugin_id: 'p1',
      url: 'http://x',
      events: ['a'],
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
    const toasts = useToastStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0]).toMatchObject({
      type: 'error',
      message: 'Failed to create webhook',
    });
  });

  it('useCreateOrg shows error toast', async () => {
    const { result } = renderHook(
      () => useCreateOrg(),
      { wrapper: createWrapper() },
    );
    result.current.mutate({ name: 'test org' });
    await waitFor(() => expect(result.current.isError).toBe(true));
    const toasts = useToastStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0]).toMatchObject({
      type: 'error',
      message: 'Failed to create organization',
    });
  });
});
