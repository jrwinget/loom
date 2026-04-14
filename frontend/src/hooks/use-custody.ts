import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';

export interface CustodyEntry {
  id: string;
  asset_id: string;
  action: string;
  actor_id: string;
  detail: unknown;
  ip_address: string | null;
  timestamp: string;
}

interface CustodyEntryListResponse {
  items: CustodyEntry[];
  total: number;
}

export function useAssetCustody(
  caseId: string,
  assetId: string,
): ReturnType<typeof useQuery<CustodyEntryListResponse>> {
  return useQuery({
    queryKey: queryKeys.custody.byAsset(caseId, assetId),
    queryFn: () =>
      apiClient.get<CustodyEntryListResponse>(
        `/cases/${caseId}/assets/${assetId}/custody`,
      ),
    enabled: !!caseId && !!assetId,
  });
}
