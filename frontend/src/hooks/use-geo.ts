import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';
import type { GeoAsset, GeoBounds, GeoEvent } from '@/types/geo';

interface GeoAssetListResponse {
  items: GeoAsset[];
}

interface GeoEventListResponse {
  items: GeoEvent[];
}

export function useGeoAssets(
  caseId: string,
  timeStart?: string,
  timeEnd?: string,
): ReturnType<typeof useQuery<GeoAssetListResponse>> {
  return useQuery({
    queryKey: queryKeys.geo.assets(caseId, timeStart, timeEnd),
    queryFn: () => {
      const params = new URLSearchParams();
      if (timeStart) params.set('time_start', timeStart);
      if (timeEnd) params.set('time_end', timeEnd);
      const qs = params.toString();
      return apiClient.get<GeoAssetListResponse>(
        `/cases/${caseId}/geo/assets${qs ? `?${qs}` : ''}`,
      );
    },
    enabled: !!caseId,
  });
}

export function useGeoEvents(
  caseId: string,
  timeStart?: string,
  timeEnd?: string,
): ReturnType<typeof useQuery<GeoEventListResponse>> {
  return useQuery({
    queryKey: queryKeys.geo.events(caseId, timeStart, timeEnd),
    queryFn: () => {
      const params = new URLSearchParams();
      if (timeStart) params.set('time_start', timeStart);
      if (timeEnd) params.set('time_end', timeEnd);
      const qs = params.toString();
      return apiClient.get<GeoEventListResponse>(
        `/cases/${caseId}/geo/events${qs ? `?${qs}` : ''}`,
      );
    },
    enabled: !!caseId,
  });
}

export function useGeoBounds(
  caseId: string,
): ReturnType<typeof useQuery<GeoBounds>> {
  return useQuery({
    queryKey: queryKeys.geo.bounds(caseId),
    queryFn: () => apiClient.get<GeoBounds>(`/cases/${caseId}/geo/bounds`),
    enabled: !!caseId,
  });
}
