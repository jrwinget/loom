import { useQuery } from '@tanstack/react-query';
import { ApiClientError, apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';

export interface WaveformResponse {
  // normalized amplitude peaks in [0, 1] decoded from the real audio
  peaks: number[];
}

// null is the honest "unavailable" state: peaks were never produced
// (asset still processing, or ffmpeg was absent at ingest). the player
// renders a muted message on null rather than a fabricated shape.
export function useWaveform(
  caseId: string,
  assetId: string,
): ReturnType<typeof useQuery<WaveformResponse | null>> {
  return useQuery({
    queryKey: queryKeys.waveforms.byAsset(caseId, assetId),
    queryFn: async () => {
      try {
        return await apiClient.get<WaveformResponse>(
          `/cases/${caseId}/assets/${assetId}/waveform`,
        );
      } catch (err) {
        if (err instanceof ApiClientError && err.status === 404) {
          return null;
        }
        throw err;
      }
    },
    enabled: !!caseId && !!assetId,
  });
}
