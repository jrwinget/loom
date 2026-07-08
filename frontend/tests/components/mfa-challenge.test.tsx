/// <reference types="@testing-library/jest-dom" />
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MfaChallenge } from '@/components/auth/MfaChallenge';
import { useAuthStore } from '@/stores/auth-store';

// keep the real ApiClientError so instanceof checks in the component
// see the same class the mocked client rejects with
vi.mock('@/lib/api-client', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  apiClient: {
    post: vi.fn(),
    get: vi.fn(),
  },
}));

import { ApiClientError, apiClient } from '@/lib/api-client';

const mockedPost = vi.mocked(apiClient.post);
const mockedGet = vi.mocked(apiClient.get);

describe('MfaChallenge', () => {
  beforeEach(() => {
    // seed the auth store with a pending mfa challenge token so the
    // component renders with realistic context
    useAuthStore.setState({
      token: null,
      user: null,
      mfaChallengeToken: 'challenge-abc',
    });
    mockedPost.mockReset();
    mockedGet.mockReset();
  });

  it('renders the code input and submit button', () => {
    render(<MfaChallenge />);

    expect(
      screen.getByRole('heading', { name: 'Two-Factor Authentication' }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Code')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Verify' })).toBeInTheDocument();
  });

  it('disables the submit button while the code field is empty', () => {
    render(<MfaChallenge />);

    expect(screen.getByRole('button', { name: 'Verify' })).toBeDisabled();
  });

  it('submits the entered code and stores the returned token on success', async () => {
    mockedPost.mockResolvedValueOnce({
      accessToken: 'new-jwt',
      refreshToken: 'new-refresh',
    });
    mockedGet.mockResolvedValueOnce({
      id: 'u-1',
      email: 'ada@example.org',
      displayName: 'Ada',
      role: 'admin',
    });
    const user = userEvent.setup();

    render(<MfaChallenge />);
    await user.type(screen.getByLabelText('Code'), '123456');
    await user.click(screen.getByRole('button', { name: 'Verify' }));

    await waitFor(() => {
      expect(useAuthStore.getState().token).toBe('new-jwt');
    });
    expect(mockedPost).toHaveBeenCalledWith('/auth/mfa/challenge', {
      challenge_token: 'challenge-abc',
      code: '123456',
    });
    expect(mockedGet).toHaveBeenCalledWith('/auth/me');
    expect(useAuthStore.getState().mfaChallengeToken).toBeNull();
  });

  it('disables the submit button while a request is in flight', async () => {
    // hold the promise so we can assert the pending state mid-flight
    let resolvePost: (value: unknown) => void = () => {};
    mockedPost.mockReturnValueOnce(
      new Promise((resolve) => {
        resolvePost = resolve;
      }),
    );
    const user = userEvent.setup();

    render(<MfaChallenge />);
    await user.type(screen.getByLabelText('Code'), '123456');
    await user.click(screen.getByRole('button', { name: 'Verify' }));

    expect(screen.getByRole('button', { name: 'Verifying...' })).toBeDisabled();

    resolvePost({ accessToken: 't', refreshToken: 'r' });
    mockedGet.mockResolvedValueOnce({
      id: 'u-1',
      email: 'ada@example.org',
      displayName: 'Ada',
      role: 'admin',
    });
    await waitFor(() => expect(useAuthStore.getState().token).toBe('t'));
  });

  it('surfaces the backend detail when the server rejects the code', async () => {
    mockedPost.mockRejectedValueOnce(
      new ApiClientError(401, 'challenge expired, sign in again'),
    );
    const user = userEvent.setup();

    render(<MfaChallenge />);
    await user.type(screen.getByLabelText('Code'), '000000');
    await user.click(screen.getByRole('button', { name: 'Verify' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'challenge expired, sign in again',
    );
    // verify is re-enabled so the user can retry without reloading
    expect(screen.getByRole('button', { name: 'Verify' })).not.toBeDisabled();
  });

  it('shows a rate-limit message on 429', async () => {
    mockedPost.mockRejectedValueOnce(
      new ApiClientError(429, 'rate limit exceeded'),
    );
    const user = userEvent.setup();

    render(<MfaChallenge />);
    await user.type(screen.getByLabelText('Code'), '000000');
    await user.click(screen.getByRole('button', { name: 'Verify' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Too many attempts. Wait a minute and try again.',
    );
  });

  it('distinguishes a transport failure from a rejected code', async () => {
    mockedPost.mockRejectedValueOnce(new TypeError('Load failed'));
    const user = userEvent.setup();

    render(<MfaChallenge />);
    await user.type(screen.getByLabelText('Code'), '123456');
    await user.click(screen.getByRole('button', { name: 'Verify' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      "Couldn't reach Loom. Make sure the app is running and try again.",
    );
  });

  it('clears the half-auth token when the profile fetch fails', async () => {
    mockedPost.mockResolvedValueOnce({
      accessToken: 'new-jwt',
      refreshToken: 'new-refresh',
    });
    mockedGet.mockRejectedValueOnce(new ApiClientError(500, 'boom'));
    const user = userEvent.setup();

    render(<MfaChallenge />);
    await user.type(screen.getByLabelText('Code'), '123456');
    await user.click(screen.getByRole('button', { name: 'Verify' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Verified, but could not load your profile. Try again.',
    );
    expect(useAuthStore.getState().token).toBeNull();
  });

  it('submits the form when the user presses Enter inside the code input', async () => {
    mockedPost.mockResolvedValueOnce({
      accessToken: 'jwt',
      refreshToken: 'refresh',
    });
    mockedGet.mockResolvedValueOnce({
      id: 'u-1',
      email: 'ada@example.org',
      displayName: 'Ada',
      role: 'admin',
    });
    const user = userEvent.setup();

    render(<MfaChallenge />);
    const input = screen.getByLabelText('Code');
    await user.type(input, '123456{Enter}');

    await waitFor(() => {
      expect(mockedPost).toHaveBeenCalledWith('/auth/mfa/challenge', {
        challenge_token: 'challenge-abc',
        code: '123456',
      });
    });
  });

  it('clears the mfa challenge when "Back to login" is clicked', async () => {
    const user = userEvent.setup();

    render(<MfaChallenge />);
    await user.click(screen.getByRole('button', { name: 'Back to login' }));

    expect(useAuthStore.getState().mfaChallengeToken).toBeNull();
  });
});
