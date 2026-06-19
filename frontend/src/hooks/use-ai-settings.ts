import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { useToastStore } from '@/stores/toast-store';

export interface AiSettings {
  transcriptionEngine: string;
  provider: string;
  apiBaseUrl: string;
  transcriptionModel: string;
  apiKeySet: boolean;
}

// sent verbatim (api-client does not transform request bodies), so the
// wire shape is snake_case to match the backend schema.
export interface AiSettingsUpdate {
  transcription_engine?: string;
  provider?: string;
  api_base_url?: string;
  transcription_model?: string;
  api_key?: string;
}

export interface AiProviderModel {
  id: string;
  label: string;
}

export interface AiProvider {
  id: string;
  label: string;
  group: string;
  models: AiProviderModel[];
  requiresApiKey: boolean;
  baseUrl: string;
  baseUrlEditable: boolean;
  available: boolean;
  note: string;
}

interface AiProvidersResponse {
  providers: AiProvider[];
}

const aiSettingsKey = ['settings', 'ai'] as const;
const aiProvidersKey = ['settings', 'ai', 'providers'] as const;

export function useAiSettings(): ReturnType<typeof useQuery<AiSettings>> {
  return useQuery({
    queryKey: aiSettingsKey,
    queryFn: () => apiClient.get<AiSettings>('/settings/ai'),
  });
}

export function useAiProviders(): ReturnType<typeof useQuery<AiProvider[]>> {
  return useQuery({
    queryKey: aiProvidersKey,
    queryFn: async () => {
      const res = await apiClient.get<AiProvidersResponse>(
        '/settings/ai/providers',
      );
      return res.providers;
    },
    // the catalog is static for the life of the app
    staleTime: Infinity,
  });
}

export function useUpdateAiSettings(): ReturnType<
  typeof useMutation<AiSettings, Error, AiSettingsUpdate>
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: AiSettingsUpdate) =>
      apiClient.put<AiSettings>('/settings/ai', patch),
    onSuccess: (data) => {
      queryClient.setQueryData(aiSettingsKey, data);
      useToastStore.getState().addToast({
        type: 'success',
        message: 'AI settings saved',
      });
    },
    onError: (error: Error) => {
      useToastStore.getState().addToast({
        type: 'error',
        message: error.message || 'Failed to save AI settings',
      });
    },
  });
}
