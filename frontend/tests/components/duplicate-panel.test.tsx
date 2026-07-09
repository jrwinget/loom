/// <reference types="@testing-library/jest-dom" />
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe } from 'jest-axe';
import { describe, expect, it, vi } from 'vitest';
import { DuplicatePanel } from '@/components/review/duplicate-panel';
import type {
  DuplicateCluster,
  DuplicateClusterMember,
} from '@/types/transcript';

function makeMember(
  overrides: Partial<DuplicateClusterMember> = {},
): DuplicateClusterMember {
  return {
    id: 'm1',
    assetId: 'asset-1',
    originalFilename: 'clip.mp4',
    distance: 0.125,
    isPrimary: false,
    ...overrides,
  };
}

function makeCluster(
  overrides: Partial<DuplicateCluster> = {},
): DuplicateCluster {
  return {
    id: 'cluster-1',
    caseId: 'case-1',
    status: 'pending',
    members: [makeMember(), makeMember({ id: 'm2', isPrimary: true })],
    createdAt: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('DuplicatePanel', () => {
  it('shows an empty state when there are no clusters', () => {
    render(<DuplicatePanel clusters={[]} />);

    expect(screen.getByText('No duplicate clusters found')).toBeInTheDocument();
  });

  it('reveals the member rows when a cluster is expanded', async () => {
    const user = userEvent.setup();
    render(<DuplicatePanel clusters={[makeCluster()]} />);

    expect(screen.queryByTestId('member-m1')).not.toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /2 files/ }));

    expect(screen.getByTestId('member-m1')).toBeInTheDocument();
  });

  it('renders a set-primary control only for non-primary members', async () => {
    const user = userEvent.setup();
    const onMarkPrimary = vi.fn();
    render(
      <DuplicatePanel
        clusters={[makeCluster()]}
        onMarkPrimary={onMarkPrimary}
      />,
    );

    await user.click(screen.getByRole('button', { name: /2 files/ }));
    await user.click(screen.getByRole('button', { name: 'Set primary' }));

    expect(onMarkPrimary).toHaveBeenCalledWith('cluster-1', 'asset-1');
  });

  it('reports the reviewed status when the reviewed control is used', async () => {
    const user = userEvent.setup();
    const onUpdateStatus = vi.fn();
    render(
      <DuplicatePanel
        clusters={[makeCluster()]}
        onUpdateStatus={onUpdateStatus}
      />,
    );

    await user.click(screen.getByRole('button', { name: /2 files/ }));
    await user.click(screen.getByTestId('mark-reviewed'));

    expect(onUpdateStatus).toHaveBeenCalledWith('cluster-1', 'reviewed');
  });

  it('has no accessibility violations when expanded', async () => {
    const user = userEvent.setup();
    const { container } = render(
      <DuplicatePanel
        clusters={[makeCluster()]}
        onMarkPrimary={vi.fn()}
        onUpdateStatus={vi.fn()}
      />,
    );

    await user.click(screen.getByRole('button', { name: /2 files/ }));
    expect(await axe(container)).toHaveNoViolations();
  });
});
