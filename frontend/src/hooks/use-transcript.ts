import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';
import type { TranscriptResponse } from '@/types/transcript';

export function useTranscript(
  caseId: string,
  assetId: string,
): ReturnType<typeof useQuery<TranscriptResponse>> {
  return useQuery({
    queryKey: queryKeys.transcripts.byAsset(caseId, assetId),
    queryFn: () =>
      apiClient.get<TranscriptResponse>(
        `/cases/${caseId}/assets/${assetId}/transcript`,
      ),
    enabled: !!caseId && !!assetId,
  });
}

interface StartTranscriptionResponse {
  taskId: string;
}

export function useStartTranscription(
  caseId: string,
  assetId: string,
): ReturnType<typeof useMutation<StartTranscriptionResponse, Error, void>> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () =>
      apiClient.post<StartTranscriptionResponse>(
        `/cases/${caseId}/assets/${assetId}/transcribe`,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.transcripts.byAsset(caseId, assetId),
      });
    },
  });
}
