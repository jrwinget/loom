import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';
import { useJobStore } from '@/stores/job-store';
import { useToastStore } from '@/stores/toast-store';

export interface IngestUrlPayload {
  url: string;
  submission_note?: string;
}

// the api client camelizes response keys; the old snake_case shape
// here was a lie that hid the workflow id from callers
export interface IngestUrlResponse {
  assetId: string;
  workflowId: string;
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
    onSuccess: (data, variables) => {
      useJobStore.getState().registerJob({
        workflowId: data.workflowId,
        caseId,
        kind: 'url_ingest',
        label: variables.url,
        assetId: data.assetId,
      });
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
