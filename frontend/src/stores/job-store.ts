import { create } from 'zustand';

export type JobKind =
  | 'transcription'
  | 'scene_detection'
  | 'ocr'
  | 'export'
  | 'enhancement'
  | 'url_ingest'
  | 'ingest'
  | 'bundle_import';

export type JobStatus = 'running' | 'completed' | 'failed' | 'cancelled';

export interface TrackedJob {
  workflowId: string;
  caseId: string;
  kind: JobKind;
  label: string;
  assetId?: string;
  status: JobStatus;
  error?: string | null;
  errorCode?: string | null;
  stage?: string | null;
  stepsDone?: number | null;
  stepsTotal?: number | null;
  startedAt: number;
  // re-fires the original start endpoint; in-memory only, which
  // matches the registry (in-flight work does not survive restart)
  retry?: () => void;
}

interface JobState {
  jobs: TrackedJob[];
  registerJob: (job: Omit<TrackedJob, 'status' | 'startedAt'>) => void;
  updateProgress: (
    workflowId: string,
    progress: Pick<TrackedJob, 'stage' | 'stepsDone' | 'stepsTotal'>,
  ) => void;
  resolveJob: (
    workflowId: string,
    status: JobStatus,
    error?: string | null,
    errorCode?: string | null,
  ) => void;
  dismissJob: (workflowId: string) => void;
  clearFinished: () => void;
}

// not persisted on purpose: lite workflows run in-process and do not
// survive a restart, so a rehydrated "running" entry would be a lie
export const useJobStore = create<JobState>((set) => ({
  jobs: [],
  registerJob: (job) =>
    set((s) => ({
      jobs: [
        // re-registering (retry) replaces the previous entry
        ...s.jobs.filter((j) => j.workflowId !== job.workflowId),
        { ...job, status: 'running' as const, startedAt: Date.now() },
      ],
    })),
  updateProgress: (workflowId, progress) =>
    set((s) => {
      const target = s.jobs.find((j) => j.workflowId === workflowId);
      // no-op when nothing changed: the watcher effect depends on the
      // job object, so an unconditional rewrite would loop forever
      if (
        !target ||
        (target.stage === progress.stage &&
          target.stepsDone === progress.stepsDone &&
          target.stepsTotal === progress.stepsTotal)
      ) {
        return s;
      }
      return {
        jobs: s.jobs.map((j) =>
          j.workflowId === workflowId ? { ...j, ...progress } : j,
        ),
      };
    }),
  resolveJob: (workflowId, status, error = null, errorCode = null) =>
    set((s) => ({
      jobs: s.jobs.map((j) =>
        j.workflowId === workflowId ? { ...j, status, error, errorCode } : j,
      ),
    })),
  dismissJob: (workflowId) =>
    set((s) => ({
      jobs: s.jobs.filter((j) => j.workflowId !== workflowId),
    })),
  clearFinished: () =>
    set((s) => ({
      jobs: s.jobs.filter((j) => j.status === 'running'),
    })),
}));
