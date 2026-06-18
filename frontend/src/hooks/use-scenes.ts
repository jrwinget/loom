import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';
import type { SceneInfo } from '@/types/transcript';

interface SceneListResponse {
  scenes: SceneInfo[];
}

export function useScenes(
  caseId: string,
  assetId: string,
): ReturnType<typeof useQuery<SceneInfo[]>> {
  return useQuery({
    queryKey: queryKeys.scenes.byAsset(caseId, assetId),
    queryFn: async () => {
      const res = await apiClient.get<SceneListResponse>(
        `/cases/${caseId}/assets/${assetId}/scenes`,
      );
      return res.scenes;
    },
    enabled: !!caseId && !!assetId,
  });
}

interface StartSceneDetectionResponse {
  taskId: string;
}

export function useStartSceneDetection(
  caseId: string,
  assetId: string,
): ReturnType<typeof useMutation<StartSceneDetectionResponse, Error, void>> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () =>
      apiClient.post<StartSceneDetectionResponse>(
        `/cases/${caseId}/assets/${assetId}/scenes/detect`,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.scenes.byAsset(caseId, assetId),
      });
    },
  });
}
