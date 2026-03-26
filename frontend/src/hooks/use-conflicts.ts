import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';
import type {
  ConflictDetail,
  ConflictListResponse,
  ConflictResolution,
  CreateResolutionPayload,
} from '@/types/conflict';

export function useCaseConflicts(
  caseId: string,
  resolved?: boolean,
): ReturnType<typeof useQuery<ConflictListResponse>> {
  return useQuery({
    queryKey: queryKeys.conflicts.byCase(caseId, resolved),
    queryFn: () => {
      const params =
        resolved !== undefined ? `?resolved=${String(resolved)}` : '';
      return apiClient.get<ConflictListResponse>(
        `/cases/${caseId}/conflicts${params}`,
      );
    },
    enabled: !!caseId,
  });
}

export function useEventConflicts(
  caseId: string,
  eventId: string,
): ReturnType<typeof useQuery<ConflictDetail>> {
  return useQuery({
    queryKey: queryKeys.conflicts.detail(caseId, eventId),
    queryFn: () =>
      apiClient.get<ConflictDetail>(
        `/cases/${caseId}/events/${eventId}/conflicts`,
      ),
    enabled: !!caseId && !!eventId,
  });
}

export function useCreateResolution(
  caseId: string,
  eventId: string,
): ReturnType<
  typeof useMutation<ConflictResolution, Error, CreateResolutionPayload>
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: CreateResolutionPayload) =>
      apiClient.post<ConflictResolution>(
        `/cases/${caseId}/events/${eventId}/resolutions`,
        payload,
      ),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.conflicts.detail(caseId, eventId),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.conflicts.byCase(caseId),
      });
    },
  });
}

export function useUpdateResolution(caseId: string): ReturnType<
  typeof useMutation<
    ConflictResolution,
    Error,
    {
      eventId: string;
      resolutionId: string;
      payload: CreateResolutionPayload;
    }
  >
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      eventId,
      resolutionId,
      payload,
    }: {
      eventId: string;
      resolutionId: string;
      payload: CreateResolutionPayload;
    }) =>
      apiClient.patch<ConflictResolution>(
        `/cases/${caseId}/events/${eventId}/resolutions/${resolutionId}`,
        payload,
      ),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.conflicts.detail(caseId, variables.eventId),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.conflicts.byCase(caseId),
      });
    },
  });
}
