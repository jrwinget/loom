import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { LoginPage } from '@/routes/login';
import { useAuthStore } from '@/stores/auth-store';

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    post: vi.fn(),
    get: vi.fn(),
  },
}));

import { apiClient } from '@/lib/api-client';

const mockedPost = vi.mocked(apiClient.post);
const mockedGet = vi.mocked(apiClient.get);

function renderLogin(): void {
  // LoginPage calls useFirstRunStatus() which needs a QueryClient in
  // scope. mocking apiClient means the query never resolves, so the
  // redirect effect is inert — existing MFA assertions hold.
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <LoginPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('LoginPage MFA flow', () => {
  beforeEach(() => {
    useAuthStore.setState({
      token: null,
      user: null,
      mfaChallengeToken: null,
    });
    mockNavigate.mockClear();
    mockedPost.mockReset();
    mockedGet.mockReset();
  });

  it('shows MFA challenge when login returns requires_mfa', async () => {
    const user = userEvent.setup();

    mockedPost.mockResolvedValueOnce({
      requires_mfa: true,
      challenge_token: 'test-challenge-token',
    });

    renderLogin();

    await user.type(screen.getByLabelText('Email'), 'test@example.com');
    await user.type(screen.getByLabelText('Password'), 'password123');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    await waitFor(() => {
      expect(
        screen.getByText('Two-Factor Authentication'),
      ).toBeInTheDocument();
    });
  });

  it('completes login after successful MFA verification', async () => {
    const user = userEvent.setup();

    // first call: login returns mfa challenge
    mockedPost.mockResolvedValueOnce({
      requires_mfa: true,
      challenge_token: 'test-challenge-token',
    });

    renderLogin();

    await user.type(screen.getByLabelText('Email'), 'test@example.com');
    await user.type(screen.getByLabelText('Password'), 'password123');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    await waitFor(() => {
      expect(
        screen.getByText('Two-Factor Authentication'),
      ).toBeInTheDocument();
    });

    // second call: mfa challenge returns tokens
    mockedPost.mockResolvedValueOnce({
      access_token: 'jwt-token',
      refresh_token: 'refresh-token',
    });
    mockedGet.mockResolvedValueOnce({
      id: '1',
      email: 'test@example.com',
      displayName: 'Test',
      role: 'admin',
    });

    await user.type(screen.getByLabelText('Code'), '123456');
    await user.click(screen.getByRole('button', { name: 'Verify' }));

    await waitFor(() => {
      const state = useAuthStore.getState();
      expect(state.token).toBe('jwt-token');
      expect(state.mfaChallengeToken).toBeNull();
    });
  });

  it('shows error on failed MFA code', async () => {
    const user = userEvent.setup();

    mockedPost.mockResolvedValueOnce({
      requires_mfa: true,
      challenge_token: 'test-challenge-token',
    });

    renderLogin();

    await user.type(screen.getByLabelText('Email'), 'test@example.com');
    await user.type(screen.getByLabelText('Password'), 'password123');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    await waitFor(() => {
      expect(
        screen.getByText('Two-Factor Authentication'),
      ).toBeInTheDocument();
    });

    // mfa challenge fails
    mockedPost.mockRejectedValueOnce(new Error('invalid code'));

    await user.type(screen.getByLabelText('Code'), '000000');
    await user.click(screen.getByRole('button', { name: 'Verify' }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(
        'Invalid code',
      );
    });
  });

  it('returns to login when back button clicked', async () => {
    const user = userEvent.setup();

    mockedPost.mockResolvedValueOnce({
      requires_mfa: true,
      challenge_token: 'test-challenge-token',
    });

    renderLogin();

    await user.type(screen.getByLabelText('Email'), 'test@example.com');
    await user.type(screen.getByLabelText('Password'), 'password123');
    await user.click(screen.getByRole('button', { name: 'Sign in' }));

    await waitFor(() => {
      expect(
        screen.getByText('Two-Factor Authentication'),
      ).toBeInTheDocument();
    });

    await user.click(
      screen.getByRole('button', { name: 'Back to login' }),
    );

    await waitFor(() => {
      expect(
        screen.getByText('Sign in to Loom'),
      ).toBeInTheDocument();
    });
  });
});
