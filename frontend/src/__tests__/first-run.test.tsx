/// <reference types="@testing-library/jest-dom" />
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FirstRunPage } from '@/routes/first-run';

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { apiClient } from '@/lib/api-client';
import { useAuthStore } from '@/stores/auth-store';

const mockedGet = vi.mocked(apiClient.get);
const mockedPost = vi.mocked(apiClient.post);

function renderWithProviders(initialPath = '/first-run') {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/first-run" element={<FirstRunPage />} />
          <Route path="/" element={<div>Dashboard</div>} />
          <Route path="/login" element={<div>Login</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('FirstRunPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().clearAuth();
  });

  it('redirects to / when onboarding is already complete', async () => {
    mockedGet.mockResolvedValueOnce({
      first_run_required: false,
      deployment_profile: 'server',
      data_dir: null,
    });

    renderWithProviders();

    await waitFor(() => {
      expect(screen.getByText('Dashboard')).toBeInTheDocument();
    });
  });

  it('shows the onboarding form when required', async () => {
    mockedGet.mockResolvedValueOnce({
      first_run_required: true,
      deployment_profile: 'lite',
      data_dir: '/home/user/.loom/data',
    });

    renderWithProviders();

    expect(await screen.findByText('Welcome to Loom')).toBeInTheDocument();
    expect(screen.getByText('/home/user/.loom/data')).toBeInTheDocument();
  });

  it('rejects a password shorter than 12 characters', async () => {
    mockedGet.mockResolvedValueOnce({
      first_run_required: true,
      deployment_profile: 'server',
      data_dir: null,
    });
    const user = userEvent.setup();

    renderWithProviders();
    await screen.findByText('Welcome to Loom');

    await user.type(screen.getByLabelText(/Full name/i), 'Ada Lovelace');
    await user.type(screen.getByLabelText(/Email/i), 'ada@example.org');
    await user.type(
      screen.getByLabelText('Password (minimum 12 characters)'),
      'short',
    );
    await user.type(screen.getByLabelText(/Confirm password/i), 'short');
    await user.click(
      screen.getByRole('button', { name: /Create admin account/i }),
    );

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'at least 12 characters',
    );
    expect(mockedPost).not.toHaveBeenCalled();
  });

  it('rejects when passwords do not match', async () => {
    mockedGet.mockResolvedValueOnce({
      first_run_required: true,
      deployment_profile: 'server',
      data_dir: null,
    });
    const user = userEvent.setup();

    renderWithProviders();
    await screen.findByText('Welcome to Loom');

    await user.type(screen.getByLabelText(/Full name/i), 'Ada Lovelace');
    await user.type(screen.getByLabelText(/Email/i), 'ada@example.org');
    await user.type(
      screen.getByLabelText('Password (minimum 12 characters)'),
      'correct-horse-battery',
    );
    await user.type(
      screen.getByLabelText(/Confirm password/i),
      'different-password-xx',
    );
    await user.click(
      screen.getByRole('button', { name: /Create admin account/i }),
    );

    expect(await screen.findByRole('alert')).toHaveTextContent('do not match');
    expect(mockedPost).not.toHaveBeenCalled();
  });

  it('shows the recovery codes step after successful onboarding', async () => {
    mockedGet.mockResolvedValueOnce({
      first_run_required: true,
      deployment_profile: 'server',
      data_dir: null,
    });
    const sampleCodes = [
      'aaaaa-bbbbb-ccccc-ddddd',
      'eeeee-fffff-00000-11111',
      '22222-33333-44444-55555',
      '66666-77777-88888-99999',
      'a1b2c-3d4e5-f6789-0abcd',
      'feedb-eef00-1234-cafe1',
      'deadb-eef00-1234-cafe2',
      '12345-67890-abcde-fghi0',
    ];
    mockedPost.mockResolvedValueOnce({
      user_id: 'user-123',
      access_token: 'access',
      refresh_token: 'refresh',
      password_recovery_codes: sampleCodes,
    });
    mockedGet.mockResolvedValueOnce({
      id: 'user-123',
      email: 'ada@example.org',
      displayName: 'Ada Lovelace',
      role: 'admin',
      mfaEnabled: false,
    });
    const user = userEvent.setup();

    renderWithProviders();
    await screen.findByText('Welcome to Loom');

    await user.type(screen.getByLabelText(/Full name/i), 'Ada Lovelace');
    await user.type(screen.getByLabelText(/Email/i), 'ada@example.org');
    const pw = 'correct-horse-battery-staple';
    await user.type(
      screen.getByLabelText('Password (minimum 12 characters)'),
      pw,
    );
    await user.type(screen.getByLabelText(/Confirm password/i), pw);
    await user.click(
      screen.getByRole('button', { name: /Create admin account/i }),
    );

    // dashboard should not appear yet — the codes panel intercepts.
    expect(
      await screen.findByTestId('recovery-codes-panel'),
    ).toBeInTheDocument();
    expect(screen.queryByText('Dashboard')).not.toBeInTheDocument();
    expect(screen.getAllByTestId('recovery-code')).toHaveLength(8);
    expect(useAuthStore.getState().token).toBe('access');
  });

  it('navigates to / once the operator acknowledges the codes', async () => {
    mockedGet.mockResolvedValueOnce({
      first_run_required: true,
      deployment_profile: 'server',
      data_dir: null,
    });
    mockedPost.mockResolvedValueOnce({
      user_id: 'user-123',
      access_token: 'access',
      refresh_token: 'refresh',
      password_recovery_codes: ['aaaaa-bbbbb-ccccc-ddddd'],
    });
    mockedGet.mockResolvedValueOnce({
      id: 'user-123',
      email: 'ada@example.org',
      displayName: 'Ada Lovelace',
      role: 'admin',
      mfaEnabled: false,
    });
    const user = userEvent.setup();

    renderWithProviders();
    await screen.findByText('Welcome to Loom');

    await user.type(screen.getByLabelText(/Full name/i), 'Ada Lovelace');
    await user.type(screen.getByLabelText(/Email/i), 'ada@example.org');
    const pw = 'correct-horse-battery-staple';
    await user.type(
      screen.getByLabelText('Password (minimum 12 characters)'),
      pw,
    );
    await user.type(screen.getByLabelText(/Confirm password/i), pw);
    await user.click(
      screen.getByRole('button', { name: /Create admin account/i }),
    );

    await screen.findByTestId('recovery-codes-panel');
    await user.click(screen.getByTestId('recovery-codes-ack'));
    await user.click(screen.getByRole('button', { name: /continue to loom/i }));

    await waitFor(() => {
      expect(screen.getByText('Dashboard')).toBeInTheDocument();
    });
  });

  it('surfaces a 409 conflict as a readable error', async () => {
    mockedGet.mockResolvedValueOnce({
      first_run_required: true,
      deployment_profile: 'server',
      data_dir: null,
    });
    mockedPost.mockRejectedValueOnce(new Error('first-run already completed'));
    const user = userEvent.setup();

    renderWithProviders();
    await screen.findByText('Welcome to Loom');

    await user.type(screen.getByLabelText(/Full name/i), 'Ada Lovelace');
    await user.type(screen.getByLabelText(/Email/i), 'ada@example.org');
    const pw = 'correct-horse-battery-staple';
    await user.type(
      screen.getByLabelText('Password (minimum 12 characters)'),
      pw,
    );
    await user.type(screen.getByLabelText(/Confirm password/i), pw);
    await user.click(
      screen.getByRole('button', { name: /Create admin account/i }),
    );

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /already set up/i,
    );
  });
});
