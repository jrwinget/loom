import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';

export interface EngineInfo {
  status: string;
  remedy: string | null;
  version: string | null;
}

export interface ModelInfo {
  name: string;
  sizeBytes: number;
  downloaded: boolean;
  downloadStatus: 'downloading' | 'complete' | 'failed' | null;
  bytesDone: number | null;
  bytesTotal: number | null;
  error: string | null;
}

export interface EnginesStatus {
  engines: Record<string, EngineInfo>;
  models: ModelInfo[];
}

const ENGINES_KEY = ['settings', 'engines'] as const;

function anyDownloading(data: EnginesStatus | undefined): boolean {
  return data?.models.some((m) => m.downloadStatus === 'downloading') ?? false;
}

export function useEngines(): UseQueryResult<EnginesStatus> {
  return useQuery({
    queryKey: ENGINES_KEY,
    queryFn: () => apiClient.get<EnginesStatus>('/settings/engines'),
    // poll only while a download is in flight so progress moves
    refetchInterval: (query) =>
      anyDownloading(query.state.data) ? 1500 : false,
  });
}

export function useDownloadModel(): UseMutationResult<unknown, Error, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      apiClient.post<ModelInfo>(
        `/settings/engines/models/${name}/download`,
        {},
      ),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ENGINES_KEY }),
  });
}

export function useDeleteModel(): UseMutationResult<unknown, Error, string> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      apiClient.delete<void>(`/settings/engines/models/${name}`),
    onSettled: () => queryClient.invalidateQueries({ queryKey: ENGINES_KEY }),
  });
}
