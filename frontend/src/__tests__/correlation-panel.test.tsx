/// <reference types="@testing-library/jest-dom" />
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { CorrelationPanel } from '@/components/review/correlation-panel';
import type { CorrelationCandidate } from '@/types/correlation';

function makeCandidate(
  overrides: Partial<CorrelationCandidate> = {},
): CorrelationCandidate {
  return {
    id: 'cand-1',
    case_id: 'case-1',
    start_utc: '2026-05-12T12:00:00Z',
    end_utc: '2026-05-12T12:00:30Z',
    confidence: 0.85,
    reasoning: {
      temporal: { score: 0.9 },
      geo: { score: 0.7 },
      audio: { score: null },
    },
    status: 'pending',
    decided_by: null,
    decided_at: null,
    members: [
      {
        id: 'm-1',
        asset_id: 'a-1',
        original_filename: 'camera-a.mp4',
        capture_time: '2026-05-12T12:00:00Z',
      },
      {
        id: 'm-2',
        asset_id: 'a-2',
        original_filename: 'camera-b.mp4',
        capture_time: '2026-05-12T12:00:08Z',
      },
    ],
    created_at: '2026-05-12T11:59:00Z',
    ...overrides,
  };
}

describe('CorrelationPanel', () => {
  it('shows the empty state with a scan CTA when there are no candidates', () => {
    const onScan = vi.fn();
    render(<CorrelationPanel candidates={[]} onScan={onScan} />);
    expect(screen.getByText(/no correlation candidates/i)).toBeInTheDocument();
    expect(screen.getByTestId('scan-empty')).toBeInTheDocument();
  });

  it('disables the empty-state scan button while scanning', () => {
    render(
      <CorrelationPanel
        candidates={[]}
        onScan={() => {}}
        isScanning
      />,
    );
    expect(screen.getByTestId('scan-empty')).toBeDisabled();
  });

  it('renders confidence badge, status, and member offsets', () => {
    render(<CorrelationPanel candidates={[makeCandidate()]} />);
    const conf = screen.getByTestId('confidence-badge');
    expect(conf).toHaveTextContent('85% confidence');
    expect(conf).toHaveAttribute('data-tier', 'high');
    expect(screen.getByTestId('status-badge')).toHaveTextContent('pending');
    // earliest member offsets to 0s, the second to +8s relative to it.
    expect(screen.getByTestId('member-m-1')).toHaveTextContent('0.0s');
    expect(screen.getByTestId('member-m-2')).toHaveTextContent('+8.0s');
  });

  it('classifies confidence into high/medium/low tiers', () => {
    render(
      <CorrelationPanel
        candidates={[
          makeCandidate({ id: 'hi', confidence: 0.95 }),
          makeCandidate({ id: 'med', confidence: 0.6 }),
          makeCandidate({ id: 'lo', confidence: 0.2 }),
        ]}
      />,
    );
    const badges = screen.getAllByTestId('confidence-badge');
    expect(badges[0]).toHaveAttribute('data-tier', 'high');
    expect(badges[1]).toHaveAttribute('data-tier', 'medium');
    expect(badges[2]).toHaveAttribute('data-tier', 'low');
  });

  it('calls onDecide with the candidate id and decision', async () => {
    const onDecide = vi.fn();
    const user = userEvent.setup();
    render(
      <CorrelationPanel candidates={[makeCandidate()]} onDecide={onDecide} />,
    );
    await user.click(screen.getByTestId('accept-cand-1'));
    expect(onDecide).toHaveBeenCalledWith('cand-1', 'accepted');
    await user.click(screen.getByTestId('reject-cand-1'));
    expect(onDecide).toHaveBeenCalledWith('cand-1', 'rejected');
  });

  it('hides accept/reject for already-decided candidates', () => {
    const onDecide = vi.fn();
    render(
      <CorrelationPanel
        candidates={[makeCandidate({ status: 'accepted' })]}
        onDecide={onDecide}
      />,
    );
    expect(screen.queryByTestId('accept-cand-1')).not.toBeInTheDocument();
    expect(screen.queryByTestId('reject-cand-1')).not.toBeInTheDocument();
    expect(screen.getByTestId('status-badge')).toHaveTextContent('accepted');
  });

  it('opens reasoning popover on trigger and closes on Escape', async () => {
    const user = userEvent.setup();
    render(<CorrelationPanel candidates={[makeCandidate()]} />);
    await user.click(screen.getByTestId('reasoning-trigger-cand-1'));
    const dialog = screen.getByTestId('reasoning-content-cand-1');
    expect(dialog).toHaveTextContent('temporal');
    expect(dialog).toHaveTextContent('90%');
    expect(dialog).toHaveTextContent('—'); // audio score null
    await user.keyboard('{Escape}');
    expect(
      screen.queryByTestId('reasoning-content-cand-1'),
    ).not.toBeInTheDocument();
  });

  it('falls back to "—" when capture_time is missing for all members', () => {
    render(
      <CorrelationPanel
        candidates={[
          makeCandidate({
            members: [
              {
                id: 'm-x',
                asset_id: 'a-x',
                original_filename: null,
                capture_time: null,
              },
            ],
          }),
        ]}
      />,
    );
    expect(screen.getByTestId('member-m-x')).toHaveTextContent('—');
  });

  it('shows a loading indicator when isLoading is set', () => {
    render(<CorrelationPanel candidates={[]} isLoading />);
    expect(screen.getByText(/loading correlations/i)).toBeInTheDocument();
    // empty-state CTA must not render while loading.
    expect(screen.queryByTestId('scan-empty')).not.toBeInTheDocument();
  });
});
