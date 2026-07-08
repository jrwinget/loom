import { useMutation } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { useToastStore } from '@/stores/toast-store';

interface MfaSetupResponse {
  provisioningUri: string;
  mfaEnabled: boolean;
}

interface MfaVerifyRequest {
  code: string;
}

interface MfaVerifyResponse {
  mfaEnabled: boolean;
  recoveryCodes: string[];
}

interface MfaChallengeRequest {
  challenge_token: string;
  code: string;
}

interface MfaChallengeResponse {
  accessToken: string;
  refreshToken: string;
  tokenType: string;
}

interface MfaDisableRequest {
  code: string;
}

export function useMfaSetup() {
  return useMutation({
    mutationFn: () => apiClient.post<MfaSetupResponse>('/auth/mfa/setup'),
    onError: (error: Error) => {
      useToastStore.getState().addToast({
        type: 'error',
        message: error.message || 'Failed to set up MFA',
      });
    },
  });
}

export function useMfaVerify() {
  return useMutation({
    mutationFn: (payload: MfaVerifyRequest) =>
      apiClient.post<MfaVerifyResponse>('/auth/mfa/verify', payload),
    onSuccess: () => {
      useToastStore.getState().addToast({
        type: 'success',
        message: 'MFA enabled successfully',
      });
    },
    onError: (error: Error) => {
      useToastStore.getState().addToast({
        type: 'error',
        message: error.message || 'Failed to verify MFA code',
      });
    },
  });
}

export function useMfaChallenge() {
  return useMutation({
    mutationFn: (payload: MfaChallengeRequest) =>
      apiClient.post<MfaChallengeResponse>('/auth/mfa/challenge', payload),
    onError: (error: Error) => {
      useToastStore.getState().addToast({
        type: 'error',
        message: error.message || 'Invalid MFA code',
      });
    },
  });
}

export function useMfaDisable() {
  return useMutation({
    mutationFn: (payload: MfaDisableRequest) =>
      apiClient.delete<void>('/auth/mfa', payload),
    onSuccess: () => {
      useToastStore.getState().addToast({
        type: 'success',
        message: 'MFA disabled',
      });
    },
    onError: (error: Error) => {
      useToastStore.getState().addToast({
        type: 'error',
        message: error.message || 'Failed to disable MFA',
      });
    },
  });
}
