import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useWorkflowStatus } from '@/hooks/use-workflow-status';
import { queryKeys } from '@/lib/query-keys';
import { type TrackedJob, useJobStore } from '@/stores/job-store';
import { useToastStore } from '@/stores/toast-store';

// which queries a finished job invalidates, by kind
function invalidationKeys(job: TrackedJob): readonly (readonly string[])[] {
  switch (job.kind) {
    case 'transcription':
      return job.assetId
        ? [queryKeys.transcripts.byAsset(job.caseId, job.assetId)]
        : [];
    case 'scene_detection':
      return job.assetId
        ? [queryKeys.scenes.byAsset(job.caseId, job.assetId)]
        : [];
    case 'ocr':
      return job.assetId ? [['ocr', job.caseId, job.assetId] as const] : [];
    case 'export':
      return [queryKeys.exports.byCase(job.caseId)];
    case 'url_ingest':
    case 'ingest':
      return [queryKeys.assets.byCase(job.caseId)];
    case 'bundle_import':
      // the whole case tree fills in as the import runs
      return [queryKeys.assets.byCase(job.caseId), queryKeys.cases.all];
  }
}

// one invisible poller per running job keeps the hooks rules happy
// while the number of jobs varies
function JobPoller(props: { job: TrackedJob }): null {
  const { job } = props;
  const queryClient = useQueryClient();
  const { data, isError } = useWorkflowStatus(job.caseId, job.workflowId);
  const resolveJob = useJobStore((s) => s.resolveJob);
  const updateProgress = useJobStore((s) => s.updateProgress);

  useEffect(() => {
    if (isError) {
      resolveJob(job.workflowId, 'failed', 'Could not fetch job status');
      useToastStore.getState().addToast({
        type: 'error',
        message: `${job.label}: could not fetch job status`,
      });
      return;
    }
    if (!data) return;

    if (data.status === 'running') {
      updateProgress(job.workflowId, {
        stage: data.stage,
        stepsDone: data.stepsDone,
        stepsTotal: data.stepsTotal,
      });
      return;
    }

    const failed = data.status !== 'completed';
    resolveJob(job.workflowId, data.status, data.error, data.errorCode);
    for (const key of invalidationKeys(job)) {
      void queryClient.invalidateQueries({ queryKey: key });
    }
    useToastStore.getState().addToast({
      type: failed ? 'error' : 'success',
      message: failed
        ? `${job.label} failed${data.error ? `: ${data.error}` : ''}`
        : `${job.label} finished`,
    });
  }, [data, isError, job, queryClient, resolveJob, updateProgress]);

  return null;
}

export function JobsWatcher(): React.ReactElement {
  const jobs = useJobStore((s) => s.jobs);
  return (
    <>
      {jobs
        .filter((j) => j.status === 'running')
        .map((job) => (
          <JobPoller key={job.workflowId} job={job} />
        ))}
    </>
  );
}
