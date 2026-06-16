import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';

export interface FirstRunStatus {
  first_run_required: boolean;
  deployment_profile: 'server' | 'lite';
  data_dir: string | null;
}

export interface FirstRunCompletePayload {
  admin_email: string;
  admin_password: string;
  admin_full_name: string;
}

export interface FirstRunCompleteResponse {
  user_id: string;
  access_token: string;
  refresh_token: string;
  // single-use password-recovery codes, plaintext. backend retains
  // only sha256 hashes, so this is the only time the operator sees
  // these values. eight codes; each is four hyphen-separated groups
  // of five hex chars (``a1b2c-3d4e5-f6789-0abcd``).
  password_recovery_codes: string[];
}

export const firstRunKeys = {
  status: ['first-run', 'status'] as const,
};

export function useFirstRunStatus(): ReturnType<
  typeof useQuery<FirstRunStatus>
> {
  return useQuery({
    queryKey: firstRunKeys.status,
    queryFn: () => apiClient.get<FirstRunStatus>('/first-run/status'),
    // status rarely changes; do not refetch on focus
    staleTime: 60_000,
    // intentionally inherit the QueryClient's default retry policy
    // (3 attempts, exponential backoff). the previous ``retry: false``
    // hid every login recovery affordance permanently on a single
    // transient 5xx, because the login page derives the lite/server
    // profile from this query's data field. losing the data once was
    // unrecoverable until the operator force-quit the app.
  });
}

export function useCompleteFirstRun(): ReturnType<
  typeof useMutation<FirstRunCompleteResponse, Error, FirstRunCompletePayload>
> {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: FirstRunCompletePayload) =>
      apiClient.post<FirstRunCompleteResponse>('/first-run/complete', payload),
    // flip the cached status synchronously so FirstRunGuard does not
    // bounce the freshly-onboarded admin back to /first-run off stale
    // ``first_run_required: true`` data (staleTime is 60s). setQueryData
    // over invalidateQueries avoids a refetch racing a data-dir restart.
    onSuccess: () => {
      queryClient.setQueryData<FirstRunStatus>(firstRunKeys.status, (prev) =>
        prev
          ? { ...prev, first_run_required: false }
          : {
              first_run_required: false,
              deployment_profile: 'lite',
              data_dir: null,
            },
      );
    },
  });
}
