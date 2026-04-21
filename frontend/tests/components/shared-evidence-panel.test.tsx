import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { SharedEvidencePanel } from '@/components/case/shared-evidence-panel';
import type { SharedEvidence } from '@/types/organization';

const mockIncoming: SharedEvidence[] = [
  {
    id: '1',
    sourceCaseId: 'case-a',
    targetCaseId: 'case-b',
    assetId: 'asset-1',
    originalFilename: 'protest_video.mp4',
    sharedBy: 'user-1',
    accessLevel: 'view',
    expiresAt: null,
    createdAt: '2026-01-01T00:00:00Z',
  },
];

const mockOutgoing: SharedEvidence[] = [
  {
    id: '2',
    sourceCaseId: 'case-b',
    targetCaseId: 'case-c',
    assetId: 'asset-2',
    originalFilename: 'witness_photo.jpg',
    sharedBy: 'user-1',
    accessLevel: 'annotate',
    expiresAt: null,
    createdAt: '2026-01-02T00:00:00Z',
  },
];

function renderPanel(
  props: Partial<{
    incoming: SharedEvidence[];
    outgoing: SharedEvidence[];
    isLoading: boolean;
    onRevoke: (linkId: string) => void;
  }> = {},
): void {
  render(
    <SharedEvidencePanel
      incoming={props.incoming ?? []}
      outgoing={props.outgoing ?? []}
      isLoading={props.isLoading ?? false}
      onRevoke={props.onRevoke ?? vi.fn()}
    />,
  );
}

describe('SharedEvidencePanel', () => {
  it('renders incoming shared items', () => {
    renderPanel({ incoming: mockIncoming });
    expect(screen.getByText('protest_video.mp4')).toBeInTheDocument();
    const items = screen.getAllByTestId('shared-item');
    expect(items).toHaveLength(1);
  });

  it('renders outgoing shared items with revoke button', () => {
    renderPanel({ outgoing: mockOutgoing });
    expect(screen.getByText('witness_photo.jpg')).toBeInTheDocument();
    const revokeBtn = screen.getByTestId('revoke-btn');
    expect(revokeBtn).toBeInTheDocument();
  });

  it('shows empty messages when no shared items', () => {
    renderPanel({});
    expect(screen.getByTestId('no-incoming')).toBeInTheDocument();
    expect(screen.getByTestId('no-outgoing')).toBeInTheDocument();
  });

  it('shows skeleton when loading', () => {
    renderPanel({ isLoading: true });
    const skeletons = screen.getAllByTestId('shared-skeleton');
    expect(skeletons).toHaveLength(3);
  });

  it('renders both incoming and outgoing', () => {
    renderPanel({
      incoming: mockIncoming,
      outgoing: mockOutgoing,
    });
    const items = screen.getAllByTestId('shared-item');
    expect(items).toHaveLength(2);
  });
});
