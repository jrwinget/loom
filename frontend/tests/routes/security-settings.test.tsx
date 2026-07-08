/// <reference types="@testing-library/jest-dom" />
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SecuritySettingsPage } from '@/routes/settings/security';

// keep the real ApiClientError so instanceof checks in the page see
// the same class the mocked client rejects with
vi.mock('@/lib/api-client', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  apiClient: {
    post: vi.fn(),
    get: vi.fn(),
  },
}));

import { ApiClientError, apiClient } from '@/lib/api-client';

const mockedPost = vi.mocked(apiClient.post);

describe('SecuritySettingsPage error surfacing', () => {
  beforeEach(() => {
    mockedPost.mockReset();
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
