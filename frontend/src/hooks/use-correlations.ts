import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';
import { useToastStore } from '@/stores/toast-store';
import type {
  CorrelationCandidate,
  CorrelationCandidateListResponse,
  CorrelationDecisionPayload,
  CorrelationStatus,
} from '@/types/correlation';

export function useCorrelationCandidates(
  caseId: string,
  status?: CorrelationStatus,
): ReturnType<typeof useQuery<CorrelationCandidateListResponse>> {
  return useQuery({
    queryKey: queryKeys.correlations.byCase(caseId, status),
    queryFn: () => {
      const params = status ? `?status=${status}` : '';
      return apiClient.get<CorrelationCandidateListResponse>(
        `/cases/${caseId}/correlations${params}`,
      );
    },
    enabled: !!caseId,
  });
}

type ScanMutation = ReturnType<
  typeof useMutation<CorrelationCandidateListResponse, Error, void>
>;

export function useScanCorrelations(caseId: string): ScanMutation {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () =>
      apiClient.post<CorrelationCandidateListResponse>(
        `/cases/${caseId}/correlations/scan`,
      ),
    onSuccess: () => {
      // invalidate all correlation lists for this case (any status filter)
      void queryClient.invalidateQueries({
        queryKey: ['correlations', caseId],
      });
      useToastStore.getState().addToast({
        type: 'success',
        message: 'Correlation scan complete',
      });
    },
    onError: () => {
      useToastStore.getState().addToast({
        type: 'error',
        message: 'Correlation scan failed',
      });
    },
  });
}

export interface DecideCorrelationArgs {
  candidateId: string;
  payload: CorrelationDecisionPayload;
}

type DecideMutation = ReturnType<
  typeof useMutation<CorrelationCandidate, Error, DecideCorrelationArgs>
>;

export function useDecideCorrelation(caseId: string): DecideMutation {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ candidateId, payload }: DecideCorrelationArgs) =>
      apiClient.post<CorrelationCandidate>(
        `/cases/${caseId}/correlations/${candidateId}/decide`,
        payload,
      ),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: ['correlations', caseId],
      });
      // timeline + custody likely care about accepts
      void queryClient.invalidateQueries({
        queryKey: queryKeys.timeline.events(caseId),
      });
      useToastStore.getState().addToast({
        type: 'success',
        message:
          variables.payload.status === 'accepted'
            ? 'Correlation accepted'
            : 'Correlation rejected',
      });
    },
    onError: () => {
      useToastStore.getState().addToast({
        type: 'error',
        message: 'Failed to record correlation decision',
      });
    },
  });
}
