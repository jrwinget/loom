import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';
import { useToastStore } from '@/stores/toast-store';

export interface NarrativeDraft {
  id: string;
  caseId: string;
  assetId: string | null;
  status: 'draft' | 'approved' | 'rejected';
  text: string;
  sourceEntryIds: string[];
  modelName: string;
  modelVersion: string;
  modelParams: Record<string, unknown> | null;
  generatedBy: string;
  reviewedBy: string | null;
  reviewedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

interface NarrativeDraftListResponse {
  items: NarrativeDraft[];
}

function toastError(error: Error, fallback: string): void {
  useToastStore.getState().addToast({
    type: 'error',
    message: error.message || fallback,
  });
}

export function useNarratives(
  caseId: string,
  assetId?: string,
): ReturnType<typeof useQuery<NarrativeDraft[]>> {
  return useQuery({
    queryKey: queryKeys.narratives.byCase(caseId, assetId),
    queryFn: async () => {
      const query = assetId ? `?asset_id=${assetId}` : '';
      const res = await apiClient.get<NarrativeDraftListResponse>(
        `/cases/${caseId}/narratives${query}`,
      );
      return res.items;
    },
    enabled: !!caseId,
  });
}

/**
 * draft a narrative over the case's audit log, or one asset's chain of
 * custody when assetId is given. requires case editor+ access — the
 * backend re-checks this too.
 */
export function useGenerateNarrative(
  caseId: string,
): ReturnType<typeof useMutation<NarrativeDraft, Error, string | undefined>> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (assetId?: string) =>
      apiClient.post<NarrativeDraft>(`/cases/${caseId}/narratives`, {
        asset_id: assetId ?? null,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.narratives.byCase(caseId),
      });
    },
    onError: (error: Error) =>
      toastError(error, 'Could not generate a narrative'),
  });
}

export function useApproveNarrative(
  caseId: string,
): ReturnType<typeof useMutation<NarrativeDraft, Error, string>> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (narrativeId: string) =>
      apiClient.post<NarrativeDraft>(
        `/cases/${caseId}/narratives/${narrativeId}/approve`,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.narratives.byCase(caseId),
      });
    },
    onError: (error: Error) => toastError(error, 'Could not approve'),
  });
}

export function useRejectNarrative(
  caseId: string,
): ReturnType<typeof useMutation<NarrativeDraft, Error, string>> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (narrativeId: string) =>
      apiClient.post<NarrativeDraft>(
        `/cases/${caseId}/narratives/${narrativeId}/reject`,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.narratives.byCase(caseId),
      });
    },
    onError: (error: Error) => toastError(error, 'Could not reject'),
  });
}
