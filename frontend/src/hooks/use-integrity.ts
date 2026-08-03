import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';
import { useToastStore } from '@/stores/toast-store';

export interface IntegrityResult {
  assetId: string;
  storageKey: string;
  expectedSha256: string;
  actualSha256: string;
  expectedSha512: string;
  actualSha512: string;
  sha256Match: boolean;
  sha512Match: boolean;
  passed: boolean;
  verifiedAt: string;
}

export interface CaseIntegrityResult {
  caseId: string;
  totalAssets: number;
  passedCount: number;
  failedCount: number;
  results: IntegrityResult[];
  verifiedAt: string;
}

// the report mirrors the backend's read-only summary: stored hashes,
// recency, and the recorded verification history
export interface IntegrityReport {
  assetId: string;
  caseId: string;
  originalFilename: string;
  sha256Hash: string;
  sha512Hash: string;
  lastVerifiedAt: string | null;
  lastVerificationOk: boolean | null;
  reportGeneratedAt: string;
  [key: string]: unknown;
}

function toastError(error: Error, fallback: string): void {
  useToastStore.getState().addToast({
    type: 'error',
    message: error.message || fallback,
  });
}

/**
 * re-hash one asset's stored bytes against its ingest digests. this
 * mutates evidence state (it appends a custody entry), so it is a
 * mutation, not a query.
 */
export function useVerifyAsset(
  caseId: string,
): ReturnType<typeof useMutation<IntegrityResult, Error, string>> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (assetId: string) =>
      apiClient.post<IntegrityResult>(
        `/cases/${caseId}/assets/${assetId}/verify`,
      ),
    onSuccess: (result, assetId) => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.assets.byCase(caseId),
      });
      void queryClient.invalidateQueries({
        queryKey: queryKeys.custody.byAsset(caseId, assetId),
      });
      useToastStore.getState().addToast({
        type: result.passed ? 'success' : 'error',
        message: result.passed
          ? 'Integrity verified — hashes match'
          : 'Integrity check FAILED — stored bytes do not match',
      });
    },
    onError: (error: Error) => toastError(error, 'Verification failed'),
  });
}

/** verify every asset in the case and summarize pass/fail. */
export function useVerifyCase(
  caseId: string,
): ReturnType<typeof useMutation<CaseIntegrityResult, Error, void>> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () =>
      apiClient.post<CaseIntegrityResult>(`/cases/${caseId}/verify`),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.assets.byCase(caseId),
      });
    },
    onError: (error: Error) => toastError(error, 'Verification failed'),
  });
}

/**
 * fetch the read-only integrity report and hand it to the caller as
 * a downloaded json file — the artifact an attorney attaches to a
 * declaration.
 */
export function useDownloadIntegrityReport(
  caseId: string,
): ReturnType<typeof useMutation<IntegrityReport, Error, string>> {
  return useMutation({
    mutationFn: (assetId: string) =>
      apiClient.get<IntegrityReport>(
        `/cases/${caseId}/assets/${assetId}/integrity-report`,
      ),
    onSuccess: (report) => {
      const blob = new Blob([JSON.stringify(report, null, 2)], {
        type: 'application/json',
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `integrity-report-${report.assetId}.json`;
      link.click();
      URL.revokeObjectURL(url);
    },
    onError: (error: Error) =>
      toastError(error, 'Could not fetch the integrity report'),
  });
}
