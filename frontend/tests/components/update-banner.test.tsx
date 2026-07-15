/// <reference types="@testing-library/jest-dom" />
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { UpdateBanner } from '@/components/layout/update-banner';

vi.mock('@/lib/tauri-bridge', () => ({
  checkForUpdate: vi.fn(),
  installUpdate: vi.fn(),
}));

import { checkForUpdate, installUpdate } from '@/lib/tauri-bridge';

const mockedCheck = vi.mocked(checkForUpdate);
const mockedInstall = vi.mocked(installUpdate);

async function renderAndTick(): Promise<void> {
  render(<UpdateBanner />);
  // the passive check fires 15s after mount, off the boot path
  await act(async () => {
    await vi.advanceTimersByTimeAsync(15_000);
  });
}

describe('UpdateBanner', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockedCheck.mockReset();
    mockedInstall.mockReset();
  });

  it('renders nothing when no update is available', async () => {
    mockedCheck.mockResolvedValue(null);
    await renderAndTick();
    expect(screen.queryByTestId('update-banner')).not.toBeInTheDocument();
  });

  it('explains verification and the expected os notice', async () => {
    mockedCheck.mockResolvedValue({ version: '0.3.0', notes: null });
    await renderAndTick();

    // the trust story rides with the consent moment: updates verify
    // against the pinned key, and any smartscreen notice is expected
    // because the project ships without paid os certificates.
    const banner = screen.getByTestId('update-banner');
    expect(banner).toHaveTextContent(/verified against loom's update key/i);
    expect(banner).toHaveTextContent(/community-built/i);
  });

  it('offers the update and installs only on click', async () => {
    mockedCheck.mockResolvedValue({ version: '0.3.0', notes: null });
    mockedInstall.mockResolvedValue();
    await renderAndTick();

    expect(screen.getByTestId('update-banner')).toHaveTextContent(
      'Loom 0.3.0 is available.',
    );
    // consent-first: nothing installs from the check alone
    expect(mockedInstall).not.toHaveBeenCalled();

    await act(async () => {
      fireEvent.click(screen.getByTestId('update-install'));
    });
    expect(mockedInstall).toHaveBeenCalledOnce();
  });

  it('dismisses without installing', async () => {
    mockedCheck.mockResolvedValue({ version: '0.3.0', notes: null });
    await renderAndTick();

    await act(async () => {
      fireEvent.click(screen.getByTestId('update-dismiss'));
    });

    expect(screen.queryByTestId('update-banner')).not.toBeInTheDocument();
    expect(mockedInstall).not.toHaveBeenCalled();
  });

  it('surfaces an install failure inline', async () => {
    mockedCheck.mockResolvedValue({ version: '0.3.0', notes: null });
    mockedInstall.mockRejectedValue(new Error('signature mismatch'));
    await renderAndTick();

    await act(async () => {
      fireEvent.click(screen.getByTestId('update-install'));
    });

    expect(screen.getByRole('alert')).toHaveTextContent(
      'signature mismatch',
    );
    // the operator can retry
    expect(screen.getByTestId('update-install')).not.toBeDisabled();
  });
});
