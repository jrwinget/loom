import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';
import type {
  CreatePluginPayload,
  CreateWebhookPayload,
  Plugin,
  PluginListResponse,
  UpdatePluginPayload,
  Webhook,
  WebhookDeliveryListResponse,
  WebhookListResponse,
} from '@/types/plugin';

export function usePlugins(): ReturnType<typeof useQuery<PluginListResponse>> {
  return useQuery({
    queryKey: queryKeys.plugins.all,
    queryFn: () => apiClient.get<PluginListResponse>('/plugins'),
  });
}

export function usePlugin(id: string): ReturnType<typeof useQuery<Plugin>> {
  return useQuery({
    queryKey: queryKeys.plugins.detail(id),
    queryFn: () => apiClient.get<Plugin>(`/plugins/${id}`),
    enabled: !!id,
  });
}

export function useCreatePlugin(): ReturnType<
  typeof useMutation<Plugin, Error, CreatePluginPayload>
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CreatePluginPayload) =>
      apiClient.post<Plugin>('/plugins', payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.plugins.all,
      });
    },
  });
}

export function useUpdatePlugin(
  id: string,
): ReturnType<typeof useMutation<Plugin, Error, UpdatePluginPayload>> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: UpdatePluginPayload) =>
      apiClient.patch<Plugin>(`/plugins/${id}`, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.plugins.all,
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.plugins.detail(id),
      });
    },
  });
}

export function useDeletePlugin(): ReturnType<
  typeof useMutation<void, Error, string>
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (pluginId: string) =>
      apiClient.delete<void>(`/plugins/${pluginId}`),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.plugins.all,
      });
    },
  });
}

export function useWebhooks(
  pluginId: string,
): ReturnType<typeof useQuery<WebhookListResponse>> {
  return useQuery({
    queryKey: queryKeys.plugins.webhooks(pluginId),
    queryFn: () =>
      apiClient.get<WebhookListResponse>(`/plugins/${pluginId}/webhooks`),
    enabled: !!pluginId,
  });
}

export function useCreateWebhook(
  pluginId: string,
): ReturnType<typeof useMutation<Webhook, Error, CreateWebhookPayload>> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CreateWebhookPayload) =>
      apiClient.post<Webhook>(`/plugins/${pluginId}/webhooks`, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.plugins.webhooks(pluginId),
      });
    },
  });
}

export function useWebhookDeliveries(
  pluginId: string,
  webhookId: string,
): ReturnType<typeof useQuery<WebhookDeliveryListResponse>> {
  return useQuery({
    queryKey: queryKeys.plugins.deliveries(pluginId, webhookId),
    queryFn: () =>
      apiClient.get<WebhookDeliveryListResponse>(
        `/plugins/${pluginId}/webhooks/${webhookId}/deliveries`,
      ),
    enabled: !!pluginId && !!webhookId,
  });
}
