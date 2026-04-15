import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ClusterReview } from '@/components/timeline/cluster-review';
import type { EventCluster } from '@/types/cluster';

function makeCluster(
  overrides: Partial<EventCluster> = {},
): EventCluster {
  return {
    id: 'cluster-1',
    caseId: 'case-1',
    status: 'proposed',
    proposedTitle: 'Protest at City Hall',
    proposedDescription: null,
    timeWindowStart: '2026-01-15T10:00:00Z',
    timeWindowEnd: '2026-01-15T10:05:00Z',
    eventId: null,
    items: [
      {
        id: 'item-1',
        assetId: 'asset-1',
        originalFilename: 'video-001.mp4',
        contentType: 'video/mp4',
        contentId: 'seg-1',
        absoluteTimeStart: '2026-01-15T10:00:00Z',
        absoluteTimeEnd: '2026-01-15T10:01:00Z',
        textPreview: 'crowd gathers at entrance',
      },
      {
        id: 'item-2',
        assetId: 'asset-1',
        originalFilename: 'video-001.mp4',
        contentType: 'video/mp4',
        contentId: 'seg-2',
        absoluteTimeStart: '2026-01-15T10:02:00Z',
        absoluteTimeEnd: '2026-01-15T10:03:00Z',
        textPreview: null,
      },
      {
        id: 'item-3',
        assetId: 'asset-2',
        originalFilename: 'photo-set.zip',
        contentType: 'image/jpeg',
        contentId: 'img-1',
        absoluteTimeStart: '2026-01-15T10:01:00Z',
        absoluteTimeEnd: null,
        textPreview: null,
      },
    ],
    ...overrides,
  };
}

function renderWithProviders(ui: React.ReactElement): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  render(
    <QueryClientProvider client={queryClient}>
      {ui}
    </QueryClientProvider>,
  );
}

describe('ClusterReview', () => {
  it('renders cluster cards', () => {
    const clusters = [
      makeCluster({ id: 'c1', proposedTitle: 'Cluster A' }),
      makeCluster({ id: 'c2', proposedTitle: 'Cluster B' }),
    ];
    renderWithProviders(
      <ClusterReview caseId="case-1" clusters={clusters} />,
    );

    expect(screen.getByText('Cluster A')).toBeInTheDocument();
    expect(screen.getByText('Cluster B')).toBeInTheDocument();
  });

  it('shows accept button for proposed clusters', () => {
    const clusters = [makeCluster({ status: 'proposed' })];
    renderWithProviders(
      <ClusterReview caseId="case-1" clusters={clusters} />,
    );

    const acceptBtn = screen.getByTestId('accept-cluster-btn');
    expect(acceptBtn).toBeInTheDocument();
    expect(acceptBtn).toHaveTextContent('Accept');
  });

  it('groups items by asset', () => {
    const clusters = [makeCluster()];
    renderWithProviders(
      <ClusterReview caseId="case-1" clusters={clusters} />,
    );

    // two asset groups: asset-1 and asset-2
    expect(
      screen.getByTestId('asset-group-asset-1'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('asset-group-asset-2'),
    ).toBeInTheDocument();
  });

  it('shows empty state when no clusters', () => {
    renderWithProviders(
      <ClusterReview caseId="case-1" clusters={[]} />,
    );

    expect(
      screen.getByText('No clusters to review'),
    ).toBeInTheDocument();
  });

  it('shows status badge with correct color', () => {
    const clusters = [
      makeCluster({ id: 'c1', status: 'proposed' }),
      makeCluster({ id: 'c2', status: 'accepted' }),
      makeCluster({ id: 'c3', status: 'rejected' }),
    ];
    renderWithProviders(
      <ClusterReview caseId="case-1" clusters={clusters} />,
    );

    const badges = screen.getAllByTestId('cluster-status-badge');
    expect(badges).toHaveLength(3);
    expect(badges[0].className).toContain('blue');
    expect(badges[1].className).toContain('green');
    expect(badges[2].className).toContain('gray');
  });

  it('does not show accept/reject for non-proposed clusters', () => {
    const clusters = [makeCluster({ status: 'accepted' })];
    renderWithProviders(
      <ClusterReview caseId="case-1" clusters={clusters} />,
    );

    expect(
      screen.queryByTestId('accept-cluster-btn'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('reject-cluster-btn'),
    ).not.toBeInTheDocument();
  });
});
