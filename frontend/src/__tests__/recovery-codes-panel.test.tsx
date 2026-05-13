/// <reference types="@testing-library/jest-dom" />
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { RecoveryCodesPanel } from '@/components/auth/RecoveryCodesPanel';

const SAMPLE_CODES = [
  'aaaaa-bbbbb-ccccc-ddddd',
  'eeeee-fffff-00000-11111',
  '22222-33333-44444-55555',
  '66666-77777-88888-99999',
  'a1b2c-3d4e5-f6789-0abcd',
  'feedb-eef00-1234-cafe1',
  'deadb-eef00-1234-cafe2',
  '12345-67890-abcde-fghi0',
];

describe('RecoveryCodesPanel', () => {
  it('renders all supplied codes', () => {
    render(
      <RecoveryCodesPanel codes={SAMPLE_CODES} onAcknowledge={vi.fn()} />,
    );

    const items = screen.getAllByTestId('recovery-code');
    expect(items).toHaveLength(SAMPLE_CODES.length);
    expect(items[0]).toHaveTextContent(SAMPLE_CODES[0]);
  });

  it('keeps the continue button disabled until the acknowledgment is checked', async () => {
    const onAck = vi.fn();
    const user = userEvent.setup();
    render(<RecoveryCodesPanel codes={SAMPLE_CODES} onAcknowledge={onAck} />);

    const continueBtn = screen.getByRole('button', {
      name: /continue to loom/i,
    });
    expect(continueBtn).toBeDisabled();

    await user.click(screen.getByTestId('recovery-codes-ack'));
    expect(continueBtn).toBeEnabled();

    await user.click(continueBtn);
    expect(onAck).toHaveBeenCalledTimes(1);
  });

  it('flips the copy button to "Copied!" after a successful clipboard write', async () => {
    // jsdom ships a functional navigator.clipboard, so the copy path
    // exercises a real promise resolution. that resolution drives the
    // ui state transition we care about: the button label becoming
    // "Copied!" within the 2s window.
    const user = userEvent.setup();

    render(
      <RecoveryCodesPanel codes={SAMPLE_CODES} onAcknowledge={vi.fn()} />,
    );

    await user.click(screen.getByRole('button', { name: /copy/i }));

    expect(
      await screen.findByRole('button', { name: /copied/i }),
    ).toBeInTheDocument();
  });
});
