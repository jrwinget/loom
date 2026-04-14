import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';
import type { DuplicateCluster } from '@/types/transcript';

interface DuplicateListResponse {
  clusters: DuplicateCluster[];
  total: number;
}

export function useDuplicates(
  caseId: string,
): ReturnType<typeof useQuery<DuplicateCluster[]>> {
  return useQuery({
    queryKey: queryKeys.duplicates.byCase(caseId),
    queryFn: async () => {
      const res = await apiClient.get<DuplicateListResponse>(
        `/cases/${caseId}/duplicates`,
      );
      return res.clusters;
    },
    enabled: !!caseId,
  });
}

interface ScanResponse {
  taskId: string;
}

export function useScanDuplicates(
  caseId: string,
): ReturnType<typeof useMutation<ScanResponse, Error, void>> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () =>
      apiClient.post<ScanResponse>(`/cases/${caseId}/duplicates/scan`),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.duplicates.byCase(caseId),
      });
    },
  });
}

interface UpdateClusterVars {
  caseId: string;
  clusterId: string;
  status: string;
  primaryAssetId?: string;
}

export function useUpdateCluster(): ReturnType<
  typeof useMutation<DuplicateCluster, Error, UpdateClusterVars>
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      caseId,
      clusterId,
      status,
      primaryAssetId,
    }: UpdateClusterVars) =>
      apiClient.patch<DuplicateCluster>(
        `/cases/${caseId}/duplicates/${clusterId}`,
        { status, primary_asset_id: primaryAssetId },
      ),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.duplicates.byCase(variables.caseId),
      });
    },
  });
}
