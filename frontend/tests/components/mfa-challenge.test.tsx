/// <reference types="@testing-library/jest-dom" />
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { MfaChallenge } from '@/components/auth/MfaChallenge';
import { useAuthStore } from '@/stores/auth-store';

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    post: vi.fn(),
    get: vi.fn(),
  },
}));

import { apiClient } from '@/lib/api-client';

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
      access_token: 'new-jwt',
      refresh_token: 'new-refresh',
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

    expect(
      screen.getByRole('button', { name: 'Verifying...' }),
    ).toBeDisabled();

    resolvePost({ access_token: 't', refresh_token: 'r' });
    mockedGet.mockResolvedValueOnce({
      id: 'u-1',
      email: 'ada@example.org',
      displayName: 'Ada',
      role: 'admin',
    });
    await waitFor(() => expect(useAuthStore.getState().token).toBe('t'));
  });

  it('shows an error alert when the server rejects the code', async () => {
    mockedPost.mockRejectedValueOnce(new Error('401'));
    const user = userEvent.setup();

    render(<MfaChallenge />);
    await user.type(screen.getByLabelText('Code'), '000000');
    await user.click(screen.getByRole('button', { name: 'Verify' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Invalid code. Please try again.',
    );
    // verify is re-enabled so the user can retry without reloading
    expect(screen.getByRole('button', { name: 'Verify' })).not.toBeDisabled();
  });

  it('submits the form when the user presses Enter inside the code input', async () => {
    mockedPost.mockResolvedValueOnce({
      access_token: 'jwt',
      refresh_token: 'refresh',
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
