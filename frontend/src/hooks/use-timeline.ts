import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';
import type {
  CreateEventPayload,
  EvidenceLink,
  LinkEvidencePayload,
  TimelineEvent,
  TimelineEventDetail,
  UpdateEventPayload,
} from '@/types/timeline';

interface EventListResponse {
  items: TimelineEvent[];
  total: number;
}

interface TimelineResponse {
  events: TimelineEventDetail[];
}

export function useTimelineEvents(
  caseId: string,
  status?: string,
): ReturnType<typeof useQuery<EventListResponse>> {
  return useQuery({
    queryKey: queryKeys.timeline.events(caseId, status),
    queryFn: () => {
      const params = status ? `?status=${status}` : '';
      return apiClient.get<EventListResponse>(
        `/cases/${caseId}/events${params}`,
      );
    },
    enabled: !!caseId,
  });
}

export function useTimeline(
  caseId: string,
  status?: string,
): ReturnType<typeof useQuery<TimelineResponse>> {
  return useQuery({
    queryKey: queryKeys.timeline.full(caseId, status),
    queryFn: () => {
      const params = status ? `?status=${status}` : '';
      return apiClient.get<TimelineResponse>(
        `/cases/${caseId}/timeline${params}`,
      );
    },
    enabled: !!caseId,
  });
}

export function useCreateEvent(): ReturnType<
  typeof useMutation<
    TimelineEvent,
    Error,
    { caseId: string; payload: CreateEventPayload }
  >
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      caseId,
      payload,
    }: {
      caseId: string;
      payload: CreateEventPayload;
    }) => apiClient.post<TimelineEvent>(`/cases/${caseId}/events`, payload),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.timeline.events(variables.caseId),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.timeline.full(variables.caseId),
      });
    },
  });
}

export function useUpdateEvent(): ReturnType<
  typeof useMutation<
    TimelineEvent,
    Error,
    {
      caseId: string;
      eventId: string;
      payload: UpdateEventPayload;
    }
  >
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      caseId,
      eventId,
      payload,
    }: {
      caseId: string;
      eventId: string;
      payload: UpdateEventPayload;
    }) =>
      apiClient.patch<TimelineEvent>(
        `/cases/${caseId}/events/${eventId}`,
        payload,
      ),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.timeline.events(variables.caseId),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.timeline.full(variables.caseId),
      });
    },
  });
}

export function useLinkEvidence(): ReturnType<
  typeof useMutation<
    EvidenceLink,
    Error,
    {
      caseId: string;
      eventId: string;
      payload: LinkEvidencePayload;
    }
  >
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      caseId,
      eventId,
      payload,
    }: {
      caseId: string;
      eventId: string;
      payload: LinkEvidencePayload;
    }) =>
      apiClient.post<EvidenceLink>(
        `/cases/${caseId}/events/${eventId}/evidence`,
        payload,
      ),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.timeline.events(variables.caseId),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.timeline.full(variables.caseId),
      });
    },
  });
}
