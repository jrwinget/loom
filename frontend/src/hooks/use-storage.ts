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
    dataDir: wire.data_dir,
    freeBytes: wire.free_bytes,
    totalBytes: wire.total_bytes,
    originalsBytes: wire.originals_bytes,
    derivativesBytes: wire.derivatives_bytes,
    dbBytes: wire.db_bytes,
    logsBytes: wire.logs_bytes,
    assetCount: wire.asset_count,
    onSystemDrive: wire.on_system_drive,
  };
}

function mapCheck(wire: StorageCheckResultWire): StorageCheckResult {
  return {
    writable: wire.writable,
    writableReason: wire.writable_reason,
    freeBytes: wire.free_bytes,
    totalBytes: wire.total_bytes,
    onSystemDrive: wire.on_system_drive,
    advisory: wire.advisory,
    advisoryReason: wire.advisory_reason,
  };
}

function mapJob(wire: RelocationJobWire): RelocationJob {
  return {
    jobId: wire.job_id,
    status: wire.status,
    assetsCopied: wire.assets_copied,
    assetsTotal: wire.assets_total,
    bytesCopied: wire.bytes_copied,
    bytesTotal: wire.bytes_total,
    error: wire.error,
    startedAt: wire.started_at,
    completedAt: wire.completed_at,
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
      return wire.job_id;
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
