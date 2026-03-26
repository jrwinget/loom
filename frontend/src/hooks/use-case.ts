import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';
import type {
  Case,
  CaseMember,
  CreateCasePayload,
  UpdateCasePayload,
} from '@/types';

export function useCases(): ReturnType<typeof useQuery<Case[]>> {
  return useQuery({
    queryKey: queryKeys.cases.all,
    queryFn: () => apiClient.get<Case[]>('/cases'),
  });
}

export function useCase(id: string): ReturnType<typeof useQuery<Case>> {
  return useQuery({
    queryKey: queryKeys.cases.detail(id),
    queryFn: () => apiClient.get<Case>(`/cases/${id}`),
    enabled: !!id,
  });
}

export function useCreateCase(): ReturnType<
  typeof useMutation<Case, Error, CreateCasePayload>
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CreateCasePayload) =>
      apiClient.post<Case>('/cases', payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.cases.all,
      });
    },
  });
}

export function useUpdateCase(): ReturnType<
  typeof useMutation<Case, Error, { id: string; payload: UpdateCasePayload }>
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: UpdateCasePayload }) =>
      apiClient.patch<Case>(`/cases/${id}`, payload),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.cases.detail(variables.id),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.cases.all,
      });
    },
  });
}

export function useCaseMembers(
  caseId: string,
): ReturnType<typeof useQuery<CaseMember[]>> {
  return useQuery({
    queryKey: queryKeys.cases.members(caseId),
    queryFn: () => apiClient.get<CaseMember[]>(`/cases/${caseId}/members`),
    enabled: !!caseId,
  });
}
