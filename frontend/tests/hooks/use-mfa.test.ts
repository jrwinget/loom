import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  useMfaChallenge,
  useMfaDisable,
  useMfaSetup,
  useMfaVerify,
} from '@/hooks/use-mfa';
import { useToastStore } from '@/stores/toast-store';

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

import { apiClient } from '@/lib/api-client';

const mockedPost = vi.mocked(apiClient.post);
const mockedDelete = vi.mocked(apiClient.delete);

function createWrapper(): React.FC<{ children: React.ReactNode }> {
  // disable retries so a 401 surfaces as isError on the first attempt
  // instead of triggering a retry storm
  const queryClient = new QueryClient({
    defaultOptions: {
      mutations: { retry: false },
      queries: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient, children });
  };
}

describe('useMfaChallenge', () => {
  beforeEach(() => {
    useToastStore.setState({ toasts: [] });
    mockedPost.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('posts the challenge token and code, returns tokens on success', async () => {
    mockedPost.mockResolvedValueOnce({
      access_token: 'jwt',
      refresh_token: 'refresh',
      token_type: 'bearer',
    });

    const { result } = renderHook(() => useMfaChallenge(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({
      challenge_token: 'challenge-abc',
      code: '123456',
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedPost).toHaveBeenCalledWith('/auth/mfa/challenge', {
      challenge_token: 'challenge-abc',
      code: '123456',
    });
    expect(result.current.data).toEqual({
      access_token: 'jwt',
      refresh_token: 'refresh',
      token_type: 'bearer',
    });
  });

  it('surfaces a 401 as an error and shows an error toast without retrying', async () => {
    mockedPost.mockRejectedValueOnce(new Error('Invalid MFA code'));

    const { result } = renderHook(() => useMfaChallenge(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({
      challenge_token: 'challenge-abc',
      code: '000000',
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(mockedPost).toHaveBeenCalledTimes(1);
    const toasts = useToastStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0]).toMatchObject({
      type: 'error',
      message: 'Invalid MFA code',
    });
  });

  it('falls back to a default error message when the error has none', async () => {
    mockedPost.mockRejectedValueOnce(new Error(''));

    const { result } = renderHook(() => useMfaChallenge(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({
      challenge_token: 'challenge-abc',
      code: '000000',
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(useToastStore.getState().toasts[0]).toMatchObject({
      type: 'error',
      message: 'Invalid MFA code',
    });
  });
});

describe('useMfaSetup', () => {
  beforeEach(() => {
    useToastStore.setState({ toasts: [] });
    mockedPost.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('posts to /auth/mfa/setup and returns the provisioning uri', async () => {
    mockedPost.mockResolvedValueOnce({
      provisioning_uri: 'otpauth://totp/Loom:user?secret=ABC',
      mfa_enabled: false,
    });

    const { result } = renderHook(() => useMfaSetup(), {
      wrapper: createWrapper(),
    });

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedPost).toHaveBeenCalledWith('/auth/mfa/setup');
    expect(result.current.data).toEqual({
      provisioning_uri: 'otpauth://totp/Loom:user?secret=ABC',
      mfa_enabled: false,
    });
  });

  it('shows an error toast when setup fails', async () => {
    mockedPost.mockRejectedValueOnce(new Error('Setup unavailable'));

    const { result } = renderHook(() => useMfaSetup(), {
      wrapper: createWrapper(),
    });

    result.current.mutate();

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(useToastStore.getState().toasts).toMatchObject([
      { type: 'error', message: 'Setup unavailable' },
    ]);
  });
});

describe('useMfaVerify', () => {
  beforeEach(() => {
    useToastStore.setState({ toasts: [] });
    mockedPost.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('accepts a valid code and returns recovery codes plus a success toast', async () => {
    mockedPost.mockResolvedValueOnce({
      mfa_enabled: true,
      recovery_codes: ['code-1', 'code-2', 'code-3'],
    });

    const { result } = renderHook(() => useMfaVerify(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ code: '123456' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedPost).toHaveBeenCalledWith('/auth/mfa/verify', {
      code: '123456',
    });
    expect(result.current.data?.recovery_codes).toHaveLength(3);
    expect(useToastStore.getState().toasts).toMatchObject([
      { type: 'success', message: 'MFA enabled successfully' },
    ]);
  });

  it('shows an error toast and does not retry when verify fails', async () => {
    mockedPost.mockRejectedValueOnce(new Error('Invalid code'));

    const { result } = renderHook(() => useMfaVerify(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ code: '000000' });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(mockedPost).toHaveBeenCalledTimes(1);
    expect(useToastStore.getState().toasts).toMatchObject([
      { type: 'error', message: 'Invalid code' },
    ]);
  });
});

describe('useMfaDisable', () => {
  beforeEach(() => {
    useToastStore.setState({ toasts: [] });
    mockedDelete.mockReset();
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it('calls DELETE /auth/mfa with the code and shows a success toast', async () => {
    mockedDelete.mockResolvedValueOnce(undefined);

    const { result } = renderHook(() => useMfaDisable(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ code: '123456' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockedDelete).toHaveBeenCalledWith('/auth/mfa', { code: '123456' });
    expect(useToastStore.getState().toasts).toMatchObject([
      { type: 'success', message: 'MFA disabled' },
    ]);
  });

  it('shows an error toast when disable fails', async () => {
    mockedDelete.mockRejectedValueOnce(new Error('Cannot disable MFA'));

    const { result } = renderHook(() => useMfaDisable(), {
      wrapper: createWrapper(),
    });

    result.current.mutate({ code: '000000' });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(useToastStore.getState().toasts).toMatchObject([
      { type: 'error', message: 'Cannot disable MFA' },
    ]);
  });
});
