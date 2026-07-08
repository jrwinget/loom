import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';
import { useToastStore } from '@/stores/toast-store';
import type {
  Case,
  CaseMember,
  CreateCasePayload,
  UpdateCasePayload,
} from '@/types';

export function useCases(): ReturnType<typeof useQuery<Case[]>> {
  return useQuery({
    queryKey: queryKeys.cases.all,
    queryFn: async () => {
      // the list endpoint returns a paginated envelope {items,total};
      // unwrap to the array the rest of the UI expects.
      const res = await apiClient.get<{ items: Case[]; total: number }>(
        '/cases',
      );
      return res.items;
    },
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
      useToastStore.getState().addToast({
        type: 'success',
        message: 'Case created',
      });
    },
    onError: (error: Error) => {
      useToastStore.getState().addToast({
        type: 'error',
        message: error.message || 'Failed to create case',
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
      useToastStore.getState().addToast({
        type: 'success',
        message: 'Case updated',
      });
    },
    onError: (error: Error) => {
      useToastStore.getState().addToast({
        type: 'error',
        message: error.message || 'Failed to update case',
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
