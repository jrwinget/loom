import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';
import type {
  AcceptPayload,
  ClusterListResponse,
  EventCluster,
  ProposePayload,
} from '@/types/cluster';

export function useClusters(
  caseId: string,
  status?: string,
): ReturnType<typeof useQuery<ClusterListResponse>> {
  return useQuery({
    queryKey: queryKeys.clusters.byCase(caseId, status),
    queryFn: () => {
      const params = status ? `?status=${status}` : '';
      return apiClient.get<ClusterListResponse>(
        `/cases/${caseId}/clusters${params}`,
      );
    },
    enabled: !!caseId,
  });
}

export function useClusterDetail(
  caseId: string,
  clusterId: string,
): ReturnType<typeof useQuery<EventCluster>> {
  return useQuery({
    queryKey: queryKeys.clusters.detail(caseId, clusterId),
    queryFn: () =>
      apiClient.get<EventCluster>(`/cases/${caseId}/clusters/${clusterId}`),
    enabled: !!caseId && !!clusterId,
  });
}

export function useProposeClusters(
  caseId: string,
): ReturnType<typeof useMutation<ClusterListResponse, Error, ProposePayload>> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: ProposePayload) =>
      apiClient.post<ClusterListResponse>(
        `/cases/${caseId}/clusters/propose`,
        payload,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.clusters.byCase(caseId),
      });
    },
  });
}

export function useAcceptCluster(
  caseId: string,
): ReturnType<
  typeof useMutation<
    EventCluster,
    Error,
    { clusterId: string; payload: AcceptPayload }
  >
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      clusterId,
      payload,
    }: {
      clusterId: string;
      payload: AcceptPayload;
    }) =>
      apiClient.post<EventCluster>(
        `/cases/${caseId}/clusters/${clusterId}/accept`,
        payload,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.clusters.byCase(caseId),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.timeline.events(caseId),
      });
    },
  });
}

export function useRejectCluster(
  caseId: string,
): ReturnType<typeof useMutation<EventCluster, Error, string>> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (clusterId: string) =>
      apiClient.post<EventCluster>(
        `/cases/${caseId}/clusters/${clusterId}/reject`,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.clusters.byCase(caseId),
      });
    },
  });
}

export function useMergeClusters(
  caseId: string,
): ReturnType<typeof useMutation<EventCluster, Error, string[]>> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (clusterIds: string[]) =>
      apiClient.post<EventCluster>(`/cases/${caseId}/clusters/merge`, {
        cluster_ids: clusterIds,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.clusters.byCase(caseId),
      });
    },
  });
}
