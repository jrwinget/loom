import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';
import { useToastStore } from '@/stores/toast-store';
import type { Organization, OrgMember } from '@/types/organization';

interface OrgListResponse {
  items: Organization[];
  total: number;
}

export function useOrganizations(): ReturnType<
  typeof useQuery<Organization[]>
> {
  return useQuery({
    queryKey: queryKeys.organizations.all,
    queryFn: async () => {
      const res = await apiClient.get<OrgListResponse>('/organizations');
      return res.items;
    },
  });
}

export function useOrg(
  orgId: string,
): ReturnType<typeof useQuery<Organization>> {
  return useQuery({
    queryKey: queryKeys.organizations.detail(orgId),
    queryFn: () => apiClient.get<Organization>(`/organizations/${orgId}`),
    enabled: !!orgId,
  });
}

export function useCreateOrg(): ReturnType<
  typeof useMutation<
    Organization,
    Error,
    { name: string; description?: string }
  >
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { name: string; description?: string }) =>
      apiClient.post<Organization>('/organizations', payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.organizations.all,
      });
      useToastStore.getState().addToast({
        type: 'success',
        message: 'Organization created',
      });
    },
    onError: () => {
      useToastStore.getState().addToast({
        type: 'error',
        message: 'Failed to create organization',
      });
    },
  });
}

export function useOrgMembers(
  orgId: string,
): ReturnType<typeof useQuery<OrgMember[]>> {
  return useQuery({
    queryKey: queryKeys.organizations.members(orgId),
    queryFn: () =>
      apiClient.get<OrgMember[]>(`/organizations/${orgId}/members`),
    enabled: !!orgId,
  });
}
