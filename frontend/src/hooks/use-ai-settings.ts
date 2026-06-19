import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { useToastStore } from '@/stores/toast-store';

export interface AiSettings {
  transcriptionEngine: string;
  apiBaseUrl: string;
  transcriptionModel: string;
  apiKeySet: boolean;
}

// sent verbatim (api-client does not transform request bodies), so the
// wire shape is snake_case to match the backend schema.
export interface AiSettingsUpdate {
  transcription_engine?: string;
  api_base_url?: string;
  transcription_model?: string;
  api_key?: string;
}

const aiSettingsKey = ['settings', 'ai'] as const;

export function useAiSettings(): ReturnType<typeof useQuery<AiSettings>> {
  return useQuery({
    queryKey: aiSettingsKey,
    queryFn: () => apiClient.get<AiSettings>('/settings/ai'),
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
