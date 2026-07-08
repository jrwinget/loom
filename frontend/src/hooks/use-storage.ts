import { useMutation, useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';
import { useToastStore } from '@/stores/toast-store';
import type {
  RelocateAcceptedResponseWire,
  RelocateRequest,
  RelocationJob,
  RelocationJobWire,
  StorageCheckRequest,
  StorageCheckResult,
  StorageCheckResultWire,
  StorageUsage,
  StorageUsageWire,
} from '@/types/storage';

// poll cadence for an in-progress relocation job.
const RELOCATION_POLL_MS = 1000;
const STORAGE_USAGE_STALE_MS = 30_000;

function mapUsage(wire: StorageUsageWire): StorageUsage {
  return {
    dataDir: wire.dataDir,
    freeBytes: wire.freeBytes,
    totalBytes: wire.totalBytes,
    originalsBytes: wire.originalsBytes,
    derivativesBytes: wire.derivativesBytes,
    dbBytes: wire.dbBytes,
    logsBytes: wire.logsBytes,
    assetCount: wire.assetCount,
    onSystemDrive: wire.onSystemDrive,
  };
}

function mapCheck(wire: StorageCheckResultWire): StorageCheckResult {
  return {
    writable: wire.writable,
    writableReason: wire.writableReason,
    freeBytes: wire.freeBytes,
    totalBytes: wire.totalBytes,
    onSystemDrive: wire.onSystemDrive,
    advisory: wire.advisory,
    advisoryReason: wire.advisoryReason,
  };
}

function mapJob(wire: RelocationJobWire): RelocationJob {
  return {
    jobId: wire.jobId,
    status: wire.status,
    assetsCopied: wire.assetsCopied,
    assetsTotal: wire.assetsTotal,
    bytesCopied: wire.bytesCopied,
    bytesTotal: wire.bytesTotal,
    error: wire.error,
    startedAt: wire.startedAt,
    completedAt: wire.completedAt,
  };
}

export interface UseStorageUsageOptions {
  enabled?: boolean;
}

export function useStorageUsage(
  options: UseStorageUsageOptions = {},
): ReturnType<typeof useQuery<StorageUsage>> {
  const { enabled = true } = options;
  return useQuery({
    queryKey: queryKeys.storage.usage,
    queryFn: async () => {
      const wire = await apiClient.get<StorageUsageWire>('/storage/usage');
      return mapUsage(wire);
    },
    enabled,
    staleTime: STORAGE_USAGE_STALE_MS,
    // lite-only endpoint; do not retry 404s from server-profile installs.
    retry: 0,
  });
}

export function useStorageCheck(): ReturnType<
  typeof useMutation<StorageCheckResult, Error, StorageCheckRequest>
> {
  return useMutation({
    mutationFn: async (payload) => {
      const wire = await apiClient.post<StorageCheckResultWire>(
        '/storage/check',
        {
          path: payload.path,
          estimated_batch_size: payload.estimatedBatchSize,
        },
      );
      return mapCheck(wire);
    },
  });
}

export function useRelocateStorage(): ReturnType<
  typeof useMutation<string, Error, RelocateRequest>
> {
  return useMutation({
    mutationFn: async (payload) => {
      const wire = await apiClient.post<RelocateAcceptedResponseWire>(
        '/storage/relocate',
        { target_path: payload.targetPath },
      );
      return wire.jobId;
    },
    onError: (error) => {
      useToastStore.getState().addToast({
        type: 'error',
        message: error.message || 'Failed to start storage move',
      });
    },
  });
}

export function useRelocationJob(
  jobId: string | null,
): ReturnType<typeof useQuery<RelocationJob>> {
  return useQuery({
    queryKey: queryKeys.storage.relocationJob(jobId ?? ''),
    queryFn: async () => {
      const wire = await apiClient.get<RelocationJobWire>(
        `/storage/relocate/${jobId ?? ''}`,
      );
      return mapJob(wire);
    },
    enabled: !!jobId,
    // poll while the job is still running; stop once it completes or
    // fails so we don't hammer the backend after resolution.
    refetchInterval: (query) => {
      const data = query.state.data;
      if (!data) return RELOCATION_POLL_MS;
      return data.status === 'running' ? RELOCATION_POLL_MS : false;
    },
    retry: 0,
  });
}
