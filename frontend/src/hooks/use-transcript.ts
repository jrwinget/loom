import { useCallback } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import type { StartWorkflowResponse } from '@/hooks/use-workflow-status';
import { queryKeys } from '@/lib/query-keys';
import { useJobStore } from '@/stores/job-store';
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

export function useStartTranscription(
  caseId: string,
  assetId: string,
  label?: string,
): ReturnType<typeof useMutation<StartWorkflowResponse, Error, void>> {
  const start = useCallback(
    () =>
      apiClient.post<StartWorkflowResponse>(
        `/cases/${caseId}/assets/${assetId}/transcribe`,
      ),
    [caseId, assetId],
  );

  return useMutation({
    mutationFn: start,
    onSuccess: (data) => {
      // the jobs watcher polls this workflow and invalidates the
      // transcript query when it finishes — no premature invalidation
      const register = (workflowId: string): void =>
        useJobStore.getState().registerJob({
          workflowId,
          caseId,
          kind: 'transcription',
          label: label ?? 'Asset',
          assetId,
          retry: () => {
            void start().then((next) => register(next.workflowId));
          },
        });
      register(data.workflowId);
    },
  });
}
