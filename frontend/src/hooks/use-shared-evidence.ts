import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';
import type { SharedEvidence } from '@/types/organization';

export function useIncomingShared(
  caseId: string,
): ReturnType<typeof useQuery<SharedEvidence[]>> {
  return useQuery({
    queryKey: queryKeys.sharedEvidence.incoming(caseId),
    queryFn: () =>
      apiClient.get<SharedEvidence[]>(
        `/cases/${caseId}/shared-evidence/incoming`,
      ),
    enabled: !!caseId,
  });
}

export function useOutgoingShared(
  caseId: string,
): ReturnType<typeof useQuery<SharedEvidence[]>> {
  return useQuery({
    queryKey: queryKeys.sharedEvidence.outgoing(caseId),
    queryFn: () =>
      apiClient.get<SharedEvidence[]>(
        `/cases/${caseId}/shared-evidence/outgoing`,
      ),
    enabled: !!caseId,
  });
}

export function useShareEvidence(): ReturnType<
  typeof useMutation<
    SharedEvidence,
    Error,
    {
      caseId: string;
      targetCaseId: string;
      assetId: string;
      accessLevel?: string;
      expiresAt?: string;
    }
  >
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      caseId,
      targetCaseId,
      assetId,
      accessLevel,
      expiresAt,
    }: {
      caseId: string;
      targetCaseId: string;
      assetId: string;
      accessLevel?: string;
      expiresAt?: string;
    }) =>
      apiClient.post<SharedEvidence>(`/cases/${caseId}/shared-evidence`, {
        target_case_id: targetCaseId,
        asset_id: assetId,
        access_level: accessLevel ?? 'view',
        expires_at: expiresAt,
      }),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.sharedEvidence.outgoing(variables.caseId),
      });
    },
  });
}

export function useRevokeShare(): ReturnType<
  typeof useMutation<void, Error, { caseId: string; linkId: string }>
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ caseId, linkId }: { caseId: string; linkId: string }) =>
      apiClient.delete<void>(`/cases/${caseId}/shared-evidence/${linkId}`),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.sharedEvidence.outgoing(variables.caseId),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.sharedEvidence.incoming(variables.caseId),
      });
    },
  });
}
