import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';
import { useToastStore } from '@/stores/toast-store';

export interface IngestUrlPayload {
  url: string;
  submission_note?: string;
}

export interface IngestUrlResponse {
  asset_id: string;
  workflow_id: string;
  status: 'queued';
}

export function useIngestFromUrl(
  caseId: string,
): ReturnType<typeof useMutation<IngestUrlResponse, Error, IngestUrlPayload>> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: IngestUrlPayload) =>
      apiClient.post<IngestUrlResponse>(
        `/cases/${caseId}/assets/ingest-url`,
        payload,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.assets.byCase(caseId),
      });
    },
    onError: (err) => {
      useToastStore.getState().addToast({
        type: 'error',
        message: err.message || 'Failed to queue URL ingest',
      });
    },
  });
}
