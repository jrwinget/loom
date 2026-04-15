import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';

export interface AuditEntry {
  id: string;
  actor_id: string | null;
  action: string;
  resource_type: string;
  resource_id: string;
  detail: unknown;
  ip_address: string | null;
  user_agent: string | null;
  timestamp: string;
}

interface AuditEntryListResponse {
  items: AuditEntry[];
  total: number;
}

export function useCaseAudit(
  caseId: string,
  limit = 5,
): ReturnType<typeof useQuery<AuditEntryListResponse>> {
  return useQuery({
    queryKey: queryKeys.audit.byCase(caseId),
    queryFn: () =>
      apiClient.get<AuditEntryListResponse>(
        `/cases/${caseId}/audit?limit=${limit}`,
      ),
    enabled: !!caseId,
  });
}
