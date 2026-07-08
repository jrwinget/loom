import { useCallback } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import type { StartWorkflowResponse } from '@/hooks/use-workflow-status';
import { queryKeys } from '@/lib/query-keys';
import { useJobStore } from '@/stores/job-store';
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

export function useStartSceneDetection(
  caseId: string,
  assetId: string,
  label?: string,
): ReturnType<typeof useMutation<StartWorkflowResponse, Error, void>> {
  const start = useCallback(
    () =>
      apiClient.post<StartWorkflowResponse>(
        `/cases/${caseId}/assets/${assetId}/scenes/detect`,
      ),
    [caseId, assetId],
  );

  return useMutation({
    mutationFn: start,
    onSuccess: (data) => {
      // the jobs watcher polls this workflow and invalidates the
      // scenes query when it finishes — no premature invalidation
      const register = (workflowId: string): void =>
        useJobStore.getState().registerJob({
          workflowId,
          caseId,
          kind: 'scene_detection',
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
