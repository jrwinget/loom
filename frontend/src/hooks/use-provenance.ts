import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';
import type { ProvenanceListResponse } from '@/types/provenance';

export function useAssetProvenance(
  caseId: string,
  assetId: string,
): ReturnType<typeof useQuery<ProvenanceListResponse>> {
  return useQuery({
    queryKey: queryKeys.provenance.byAsset(caseId, assetId),
    queryFn: () =>
      apiClient.get<ProvenanceListResponse>(
        `/cases/${caseId}/assets/${assetId}/provenance`,
      ),
    enabled: !!caseId && !!assetId,
  });
}

export function useExportProvenance(
  caseId: string,
  exportId: string,
): ReturnType<typeof useQuery<ProvenanceListResponse>> {
  return useQuery({
    queryKey: queryKeys.provenance.byExport(caseId, exportId),
    queryFn: () =>
      apiClient.get<ProvenanceListResponse>(
        `/cases/${caseId}/exports/${exportId}/provenance`,
      ),
    enabled: !!caseId && !!exportId,
  });
}

export function useEmbedProvenance(
  caseId: string,
  exportId: string,
): ReturnType<
  typeof useMutation<{ status: string; embedded: string }, Error, void>
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () =>
      apiClient.post<{ status: string; embedded: string }>(
        `/cases/${caseId}/exports/${exportId}/provenance/embed`,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.provenance.byExport(caseId, exportId),
      });
    },
  });
}
