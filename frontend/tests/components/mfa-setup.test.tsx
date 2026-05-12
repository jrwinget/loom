/// <reference types="@testing-library/jest-dom" />
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MfaSetup } from '@/components/auth/MfaSetup';
import { useAuthStore } from '@/stores/auth-store';

// a 1x1 transparent png, just enough to render an <img src=data:...>
const SAMPLE_QR_BASE64 =
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNgAAIAAAUAAeImBZsAAAAASUVORK5CYII=';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('MfaSetup', () => {
  let fetchMock: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    useAuthStore.setState({
      token: 'test-token',
      user: null,
      mfaChallengeToken: null,
    });
    fetchMock = vi.spyOn(globalThis, 'fetch');
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the enable button before setup has been requested', () => {
    render(<MfaSetup />);
    expect(
      screen.getByRole('button', { name: 'Enable MFA' }),
    ).toBeInTheDocument();
  });

  it('shows the QR code and verification input after a successful setup call', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        provisioning_uri: 'otpauth://totp/Loom:user?secret=ABCDEF',
        qr_code_base64: SAMPLE_QR_BASE64,
      }),
    );
    const user = userEvent.setup();

    render(<MfaSetup />);
    await user.click(screen.getByRole('button', { name: 'Enable MFA' }));

    const qr = await screen.findByAltText('TOTP QR code');
    expect(qr).toHaveAttribute(
      'src',
      `data:image/png;base64,${SAMPLE_QR_BASE64}`,
    );
    expect(screen.getByLabelText('Verification code:')).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      '/api/v1/mfa/setup',
      expect.objectContaining({
        method: 'POST',
        headers: expect.objectContaining({
          Authorization: 'Bearer test-token',
        }),
      }),
    );
  });

  it('keeps the verify button disabled until 6 digits are entered', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        provisioning_uri: 'otpauth://totp/Loom:user?secret=ABCDEF',
        qr_code_base64: SAMPLE_QR_BASE64,
      }),
    );
    const user = userEvent.setup();

    render(<MfaSetup />);
    await user.click(screen.getByRole('button', { name: 'Enable MFA' }));
    await screen.findByAltText('TOTP QR code');

    const verifyButton = screen.getByRole('button', { name: 'Verify' });
    expect(verifyButton).toBeDisabled();

    await user.type(screen.getByLabelText('Verification code:'), '12345');
    expect(verifyButton).toBeDisabled();

    await user.type(screen.getByLabelText('Verification code:'), '6');
    expect(verifyButton).not.toBeDisabled();
  });

  it('shows the success state after a verify response with success=true', async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          provisioning_uri: 'otpauth://totp/Loom:user?secret=ABCDEF',
          qr_code_base64: SAMPLE_QR_BASE64,
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ success: true }));
    const user = userEvent.setup();

    render(<MfaSetup />);
    await user.click(screen.getByRole('button', { name: 'Enable MFA' }));
    await screen.findByAltText('TOTP QR code');

    await user.type(screen.getByLabelText('Verification code:'), '123456');
    await user.click(screen.getByRole('button', { name: 'Verify' }));

    expect(
      await screen.findByText('MFA enabled successfully.'),
    ).toBeInTheDocument();
    // setup view should no longer be visible
    expect(screen.queryByAltText('TOTP QR code')).not.toBeInTheDocument();
    expect(fetchMock).toHaveBeenNthCalledWith(
      2,
      '/api/v1/mfa/verify',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ code: '123456' }),
      }),
    );
  });

  it('keeps the user on the verify step and shows an alert when verify is rejected', async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          provisioning_uri: 'otpauth://totp/Loom:user?secret=ABCDEF',
          qr_code_base64: SAMPLE_QR_BASE64,
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ success: false }));
    const user = userEvent.setup();

    render(<MfaSetup />);
    await user.click(screen.getByRole('button', { name: 'Enable MFA' }));
    await screen.findByAltText('TOTP QR code');

    await user.type(screen.getByLabelText('Verification code:'), '000000');
    await user.click(screen.getByRole('button', { name: 'Verify' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'invalid code, try again',
    );
    // the verify view is still rendered, the user cannot advance
    expect(screen.getByAltText('TOTP QR code')).toBeInTheDocument();
    expect(
      screen.queryByText('MFA enabled successfully.'),
    ).not.toBeInTheDocument();
  });

  it('surfaces a server-supplied detail when verify fails with non-2xx', async () => {
    fetchMock
      .mockResolvedValueOnce(
        jsonResponse({
          provisioning_uri: 'otpauth://totp/Loom:user?secret=ABCDEF',
          qr_code_base64: SAMPLE_QR_BASE64,
        }),
      )
      .mockResolvedValueOnce(jsonResponse({ detail: 'rate limited' }, 429));
    const user = userEvent.setup();

    render(<MfaSetup />);
    await user.click(screen.getByRole('button', { name: 'Enable MFA' }));
    await screen.findByAltText('TOTP QR code');

    await user.type(screen.getByLabelText('Verification code:'), '123456');
    await user.click(screen.getByRole('button', { name: 'Verify' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('rate limited');
    expect(
      screen.queryByText('MFA enabled successfully.'),
    ).not.toBeInTheDocument();
  });

  it('surfaces a server-supplied detail when initial setup fails', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ detail: 'setup unavailable' }, 500),
    );
    const user = userEvent.setup();

    render(<MfaSetup />);
    await user.click(screen.getByRole('button', { name: 'Enable MFA' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'setup unavailable',
    );
    expect(
      screen.getByRole('button', { name: 'Enable MFA' }),
    ).toBeInTheDocument();
  });
});
