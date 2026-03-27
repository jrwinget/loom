import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';
import { useToastStore } from '@/stores/toast-store';
import type {
  CreateExportPayload,
  ExportBundle,
  ExportListResponse,
} from '@/types/export';

export function useExports(
  caseId: string,
): ReturnType<typeof useQuery<ExportListResponse>> {
  return useQuery({
    queryKey: queryKeys.exports.byCase(caseId),
    queryFn: () =>
      apiClient.get<ExportListResponse>(`/cases/${caseId}/exports`),
    enabled: !!caseId,
  });
}

export function useExport(
  caseId: string,
  exportId: string,
): ReturnType<typeof useQuery<ExportBundle>> {
  return useQuery({
    queryKey: queryKeys.exports.detail(exportId),
    queryFn: () =>
      apiClient.get<ExportBundle>(`/cases/${caseId}/exports/${exportId}`),
    enabled: !!caseId && !!exportId,
  });
}

export function useCreateExport(
  caseId: string,
): ReturnType<typeof useMutation<ExportBundle, Error, CreateExportPayload>> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CreateExportPayload) =>
      apiClient.post<ExportBundle>(`/cases/${caseId}/exports`, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.exports.byCase(caseId),
      });
      useToastStore.getState().addToast({
        type: 'success',
        message: 'Export created',
      });
    },
    onError: (error: Error) => {
      useToastStore.getState().addToast({
        type: 'error',
        message: error.message || 'Failed to create export',
      });
    },
  });
}
