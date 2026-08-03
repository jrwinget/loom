// litigation hold mutations. a hold is a case-level preservation
// lock: while active the backend refuses purge and asset deletion,
// so these are the only write paths for the hold flag. both take a
// required reason that the backend records in the audit trail.

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';
import { useToastStore } from '@/stores/toast-store';
import type { Case } from '@/types';

export function useSetHold(
  caseId: string,
): ReturnType<typeof useMutation<Case, Error, string>> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (reason: string) =>
      apiClient.post<Case>(`/cases/${caseId}/hold`, { reason }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.cases.detail(caseId),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.cases.all,
      });
      useToastStore.getState().addToast({
        type: 'success',
        message: 'Litigation hold set',
      });
    },
    onError: (error: Error) => {
      useToastStore.getState().addToast({
        type: 'error',
        message: error.message || 'Failed to set litigation hold',
      });
    },
  });
}

export function useReleaseHold(
  caseId: string,
): ReturnType<typeof useMutation<Case, Error, string>> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (reason: string) =>
      apiClient.post<Case>(`/cases/${caseId}/hold/release`, { reason }),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.cases.detail(caseId),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.cases.all,
      });
      useToastStore.getState().addToast({
        type: 'success',
        message: 'Litigation hold released',
      });
    },
    onError: (error: Error) => {
      useToastStore.getState().addToast({
        type: 'error',
        message: error.message || 'Failed to release litigation hold',
      });
    },
  });
}
