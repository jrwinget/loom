import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';

const POLL_FAST_MS = 1500;
const POLL_SLOW_MS = 5000;
// back off after ~30s of fast polling
const SLOW_AFTER_UPDATES = 20;

export interface WorkflowStatus {
  workflowId: string;
  status: 'running' | 'completed' | 'failed' | 'cancelled';
  stage: string | null;
  stepsDone: number | null;
  stepsTotal: number | null;
  error: string | null;
  errorCode: string | null;
}

// generalizes the storage-relocation polling pattern: poll while the
// workflow runs, back off, stop on a terminal state or a fetch error
// (the watcher surfaces the failure; endless 404 polling helps nobody)
export function useWorkflowStatus(
  caseId: string,
  workflowId: string,
  opts?: { enabled?: boolean },
): ReturnType<typeof useQuery<WorkflowStatus>> {
  return useQuery({
    queryKey: queryKeys.workflows.status(caseId, workflowId),
    queryFn: () =>
      apiClient.get<WorkflowStatus>(
        `/cases/${caseId}/workflows/${workflowId}/status`,
      ),
    enabled: (opts?.enabled ?? true) && !!caseId && !!workflowId,
    refetchInterval: (query) => {
      if (query.state.status === 'error') return false;
      const data = query.state.data;
      if (data && data.status !== 'running') return false;
      return query.state.dataUpdateCount > SLOW_AFTER_UPDATES
        ? POLL_SLOW_MS
        : POLL_FAST_MS;
    },
    retry: 0,
  });
}
