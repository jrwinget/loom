import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useJobStore } from '@/stores/job-store';

function register(workflowId = 'transcribe-1'): void {
  useJobStore.getState().registerJob({
    workflowId,
    caseId: 'case-1',
    kind: 'transcription',
    label: 'clip.mp4',
    assetId: 'asset-1',
  });
}

describe('job-store', () => {
  beforeEach(() => {
    useJobStore.setState({ jobs: [] });
  });

  it('registers a job as running', () => {
    register();
    const job = useJobStore.getState().jobs[0];
    expect(job.status).toBe('running');
    expect(job.label).toBe('clip.mp4');
  });

  it('re-registering replaces the previous entry', () => {
    register();
    useJobStore.getState().resolveJob('transcribe-1', 'failed', 'boom');
    register();

    const jobs = useJobStore.getState().jobs;
    expect(jobs).toHaveLength(1);
    expect(jobs[0].status).toBe('running');
    expect(jobs[0].error).toBeUndefined();
  });

  it('resolveJob records status and error', () => {
    register();
    useJobStore
      .getState()
      .resolveJob('transcribe-1', 'failed', 'no engine', 'engine_unavailable');

    const job = useJobStore.getState().jobs[0];
    expect(job.status).toBe('failed');
    expect(job.error).toBe('no engine');
    expect(job.errorCode).toBe('engine_unavailable');
  });

  it('updateProgress patches stage and steps', () => {
    register();
    useJobStore.getState().updateProgress('transcribe-1', {
      stage: 'store_transcript',
      stepsDone: 2,
      stepsTotal: 3,
    });

    const job = useJobStore.getState().jobs[0];
    expect(job.stage).toBe('store_transcript');
    expect(job.stepsDone).toBe(2);
    expect(job.stepsTotal).toBe(3);
  });

  it('dismissJob removes only the target', () => {
    register('a');
    register('b');
    useJobStore.getState().dismissJob('a');

    expect(useJobStore.getState().jobs.map((j) => j.workflowId)).toEqual(['b']);
  });

  it('clearFinished keeps running jobs', () => {
    register('a');
    register('b');
    useJobStore.getState().resolveJob('a', 'completed');

    useJobStore.getState().clearFinished();

    expect(useJobStore.getState().jobs.map((j) => j.workflowId)).toEqual(['b']);
  });

  it('keeps the retry callback for failed jobs', () => {
    const retry = vi.fn();
    useJobStore.getState().registerJob({
      workflowId: 'export-1',
      caseId: 'case-1',
      kind: 'export',
      label: 'Court bundle',
      retry,
    });
    useJobStore.getState().resolveJob('export-1', 'failed');

    useJobStore.getState().jobs[0].retry?.();
    expect(retry).toHaveBeenCalled();
  });
});
