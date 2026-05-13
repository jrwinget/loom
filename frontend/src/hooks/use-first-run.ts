import { useMutation, useQuery } from '@tanstack/react-query';
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
    retry: false,
  });
}

export function useCompleteFirstRun(): ReturnType<
  typeof useMutation<FirstRunCompleteResponse, Error, FirstRunCompletePayload>
> {
  return useMutation({
    mutationFn: (payload: FirstRunCompletePayload) =>
      apiClient.post<FirstRunCompleteResponse>('/first-run/complete', payload),
  });
}
