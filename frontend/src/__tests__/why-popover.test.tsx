/// <reference types="@testing-library/jest-dom" />
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';

import { WhyPopover } from '@/components/review/why-popover';

describe('WhyPopover', () => {
  it('hides content until trigger is clicked', () => {
    render(
      <WhyPopover
        modelName="faster-whisper"
        modelVersion="1.2.3"
        modelParams={{ model_size: 'base' }}
        confidence={0.92}
        scope="Transcript 0:00 - 0:05"
      />,
    );
    expect(
      screen.queryByTestId('why-popover-content'),
    ).not.toBeInTheDocument();
  });

  it('opens and shows provenance fields when trigger is clicked', async () => {
    const user = userEvent.setup();
    render(
      <WhyPopover
        modelName="faster-whisper"
        modelVersion="1.2.3"
        modelParams={{ model_size: 'base' }}
        confidence={0.92}
        scope="Transcript 0:00 - 0:05"
      />,
    );
    await user.click(screen.getByTestId('why-popover-trigger'));
    const content = screen.getByTestId('why-popover-content');
    expect(content).toHaveTextContent('faster-whisper');
    expect(content).toHaveTextContent('1.2.3');
    expect(content).toHaveTextContent('92%');
    expect(content).toHaveTextContent('Transcript 0:00 - 0:05');
  });

  it('renders "unknown" when model name/version are null', async () => {
    const user = userEvent.setup();
    render(
      <WhyPopover
        modelName={null}
        modelVersion={null}
        modelParams={null}
        confidence={null}
        scope="Transcript 0:00 - 0:05"
      />,
    );
    await user.click(screen.getByTestId('why-popover-trigger'));
    const content = screen.getByTestId('why-popover-content');
    expect(content).toHaveTextContent('unknown');
    expect(content).toHaveTextContent('Not reported');
  });

  it('closes when Escape is pressed', async () => {
    const user = userEvent.setup();
    render(
      <WhyPopover
        modelName="pytesseract"
        modelVersion="0.3.10"
        modelParams={null}
        confidence={0.8}
        scope="OCR region"
      />,
    );
    await user.click(screen.getByTestId('why-popover-trigger'));
    expect(screen.getByTestId('why-popover-content')).toBeInTheDocument();
    await user.keyboard('{Escape}');
    expect(
      screen.queryByTestId('why-popover-content'),
    ).not.toBeInTheDocument();
  });
});
