/// <reference types="@testing-library/jest-dom" />
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe } from 'jest-axe';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { SecuritySettingsPage } from '@/routes/settings/security';
import { useAuthStore } from '@/stores/auth-store';

// keep the real ApiClientError so instanceof checks in the page see
// the same class the mocked client rejects with
vi.mock('@/lib/api-client', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  apiClient: {
    post: vi.fn(),
    get: vi.fn(),
    delete: vi.fn(),
  },
}));

import { ApiClientError, apiClient } from '@/lib/api-client';

const mockedPost = vi.mocked(apiClient.post);
const mockedDelete = vi.mocked(apiClient.delete);

function enrollUser(mfaEnabled: boolean): void {
  useAuthStore.setState({
    token: 'test-token',
    user: {
      id: 'u1',
      email: 'a@example.com',
      displayName: 'A',
      role: 'analyst',
      mfaEnabled,
    },
  });
}

describe('SecuritySettingsPage error surfacing', () => {
  beforeEach(() => {
    mockedPost.mockReset();
    mockedDelete.mockReset();
  });

  afterEach(() => {
    useAuthStore.setState({ token: null, user: null, mfaChallengeToken: null });
  });

  it('surfaces the backend detail when setup fails', async () => {
    mockedPost.mockRejectedValueOnce(
      new ApiClientError(409, 'mfa is already enabled'),
    );
    const user = userEvent.setup();

    render(<SecuritySettingsPage />);
    await user.click(screen.getByRole('button', { name: 'Enable MFA' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'mfa is already enabled',
    );
  });

  it('surfaces the backend detail when verification fails', async () => {
    mockedPost.mockResolvedValueOnce({
      provisioningUri: 'otpauth://totp/loom?secret=abc',
    });
    mockedPost.mockRejectedValueOnce(
      new ApiClientError(400, 'code expired, scan again'),
    );
    const user = userEvent.setup();

    render(<SecuritySettingsPage />);
    await user.click(screen.getByRole('button', { name: 'Enable MFA' }));
    await user.type(
      await screen.findByPlaceholderText('Enter code from app'),
      '000000',
    );
    await user.click(screen.getByRole('button', { name: 'Verify' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'code expired, scan again',
    );
  });

  it('distinguishes a transport failure from a backend rejection', async () => {
    mockedPost.mockRejectedValueOnce(new TypeError('Load failed'));
    const user = userEvent.setup();

    render(<SecuritySettingsPage />);
    await user.click(screen.getByRole('button', { name: 'Enable MFA' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      "Couldn't reach Loom. Make sure the app is running and try again.",
    );
  });
});

const CODES = Array.from({ length: 10 }, (_, i) => `code-${i}-abcd`);

describe('SecuritySettingsPage recovery-code regeneration', () => {
  beforeEach(() => {
    mockedPost.mockReset();
    enrollUser(true);
  });

  afterEach(() => {
    useAuthStore.setState({ token: null, user: null, mfaChallengeToken: null });
  });

  it('renders fresh codes and states the old ones stop working', async () => {
    mockedPost.mockResolvedValueOnce({ recoveryCodes: CODES });
    const user = userEvent.setup();

    render(<SecuritySettingsPage />);
    await user.click(screen.getByRole('button', { name: /regenerate codes/i }));
    await user.type(
      screen.getByPlaceholderText('Enter code from app'),
      '654321',
    );
    await user.click(
      screen.getByRole('button', { name: /generate new codes/i }),
    );

    expect(await screen.findAllByTestId('recovery-code')).toHaveLength(10);
    expect(screen.getByText(/old codes no longer work/i)).toBeInTheDocument();
    expect(mockedPost).toHaveBeenCalledWith('/auth/mfa/recovery-codes', {
      code: '654321',
    });
  });

  it('surfaces the backend detail when the code is wrong', async () => {
    mockedPost.mockRejectedValueOnce(
      new ApiClientError(401, 'invalid totp code'),
    );
    const user = userEvent.setup();

    render(<SecuritySettingsPage />);
    await user.click(screen.getByRole('button', { name: /regenerate codes/i }));
    await user.type(
      screen.getByPlaceholderText('Enter code from app'),
      '000000',
    );
    await user.click(
      screen.getByRole('button', { name: /generate new codes/i }),
    );

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'invalid totp code',
    );
  });
});

describe('SecuritySettingsPage disable', () => {
  beforeEach(() => {
    mockedDelete.mockReset();
    enrollUser(true);
  });

  afterEach(() => {
    useAuthStore.setState({ token: null, user: null, mfaChallengeToken: null });
  });

  it('requires a password and confirmation before disabling', async () => {
    const user = userEvent.setup();
    render(<SecuritySettingsPage />);

    const disableBtn = screen.getByRole('button', {
      name: /disable two-factor/i,
    });
    expect(disableBtn).toBeDisabled();

    await user.type(screen.getByLabelText(/account password/i), 'hunter2xx');
    await user.click(screen.getByTestId('disable-confirm'));
    expect(disableBtn).toBeEnabled();
  });

  it('surfaces the backend detail on a 401 and leaves mfa on', async () => {
    mockedDelete.mockRejectedValueOnce(
      new ApiClientError(401, 'invalid password'),
    );
    const user = userEvent.setup();
    render(<SecuritySettingsPage />);

    await user.type(screen.getByLabelText(/account password/i), 'wrong-pass');
    await user.click(screen.getByTestId('disable-confirm'));
    await user.click(
      screen.getByRole('button', { name: /disable two-factor/i }),
    );

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'invalid password',
    );
    expect(mockedDelete).toHaveBeenCalledWith('/auth/mfa', {
      password: 'wrong-pass',
    });
    // still on the enrolled view -> the second factor was not removed.
    expect(
      screen.getByRole('heading', { name: /disable two-factor/i }),
    ).toBeInTheDocument();
  });

  it('has no accessibility violations when enrolled', async () => {
    const { container } = render(<SecuritySettingsPage />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
