/// <reference types="@testing-library/jest-dom" />
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { FactoryResetDialog } from '@/components/auth/FactoryResetDialog';

vi.mock('@/lib/tauri-bridge', () => ({
  factoryReset: vi.fn(),
}));

import { factoryReset } from '@/lib/tauri-bridge';

const mockedFactoryReset = vi.mocked(factoryReset);

describe('FactoryResetDialog', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders nothing when closed', () => {
    render(
      <FactoryResetDialog
        open={false}
        onClose={vi.fn()}
        onSuccess={vi.fn()}
      />,
    );
    expect(screen.queryByTestId('factory-reset-dialog')).not.toBeInTheDocument();
  });

  it('disables the reset button until RESET is typed exactly', async () => {
    const user = userEvent.setup();
    render(
      <FactoryResetDialog open={true} onClose={vi.fn()} onSuccess={vi.fn()} />,
    );

    const button = screen.getByRole('button', { name: /reset loom/i });
    expect(button).toBeDisabled();

    const input = screen.getByLabelText(/type .* to continue/i);
    await user.type(input, 'reset');
    expect(button).toBeDisabled();

    await user.clear(input);
    await user.type(input, 'RESET');
    expect(button).toBeEnabled();
  });

  it('invokes factoryReset on confirm and calls onSuccess', async () => {
    mockedFactoryReset.mockResolvedValueOnce(undefined);
    const onSuccess = vi.fn();
    const user = userEvent.setup();

    render(
      <FactoryResetDialog
        open={true}
        onClose={vi.fn()}
        onSuccess={onSuccess}
      />,
    );

    await user.type(screen.getByLabelText(/type .* to continue/i), 'RESET');
    await user.click(screen.getByRole('button', { name: /reset loom/i }));

    await waitFor(() => {
      expect(mockedFactoryReset).toHaveBeenCalledTimes(1);
      expect(onSuccess).toHaveBeenCalledTimes(1);
    });
  });

  it('surfaces a bridge failure as an inline error', async () => {
    mockedFactoryReset.mockRejectedValueOnce(new Error('sidecar unreachable'));
    const onSuccess = vi.fn();
    const user = userEvent.setup();

    render(
      <FactoryResetDialog
        open={true}
        onClose={vi.fn()}
        onSuccess={onSuccess}
      />,
    );

    await user.type(screen.getByLabelText(/type .* to continue/i), 'RESET');
    await user.click(screen.getByRole('button', { name: /reset loom/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      /sidecar unreachable/i,
    );
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it('closes when Cancel is pressed', async () => {
    const onClose = vi.fn();
    const user = userEvent.setup();
    render(
      <FactoryResetDialog open={true} onClose={onClose} onSuccess={vi.fn()} />,
    );

    await user.click(screen.getByRole('button', { name: /cancel/i }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
