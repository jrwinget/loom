import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';

export interface EngineCapability {
  status: 'available' | 'missing';
  remedy: string | null;
  version: string | null;
}

// wire keys are snake_case engine names; the api client camelizes
// all response keys, including this map's
export interface Capabilities {
  profile: string;
  engines: {
    transcriptionLocal: EngineCapability;
    transcriptionCloud: EngineCapability;
    ocr: EngineCapability;
    sceneDetection: EngineCapability;
    mediaPipeline: EngineCapability;
    diarization: EngineCapability;
  };
}

export function useCapabilities(): ReturnType<typeof useQuery<Capabilities>> {
  return useQuery({
    queryKey: queryKeys.capabilities,
    queryFn: () => apiClient.get<Capabilities>('/capabilities'),
    // engine availability only changes when the install changes
    staleTime: Infinity,
  });
}
