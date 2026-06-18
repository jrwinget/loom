import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { type ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { AssetDetail } from '@/components/asset/asset-detail';
import type { Asset } from '@/types/asset';

// mock the download url hook
vi.mock('@/hooks/use-assets', () => ({
  useAssetDownloadUrl: () => ({
    data: 'https://example.com/download/test.mp4',
  }),
}));

// mock the custody hook
const mockCustodyData = {
  items: [
    {
      id: 'c1',
      asset_id: 'asset-1',
      action: 'upload',
      actor_id: 'user-1',
      detail: null,
      ip_address: null,
      timestamp: '2026-03-15T16:00:00Z',
    },
    {
      id: 'c2',
      asset_id: 'asset-1',
      action: 'process_complete',
      actor_id: 'system',
      detail: null,
      ip_address: null,
      timestamp: '2026-03-15T16:05:00Z',
    },
  ],
  total: 2,
};
vi.mock('@/hooks/use-custody', () => ({
  useAssetCustody: () => ({
    data: mockCustodyData,
    isLoading: false,
  }),
}));

const mockAsset: Asset = {
  id: 'asset-1',
  caseId: 'case-1',
  originalFilename: 'protest-footage.mp4',
  storageKey: 'cases/case-1/asset-1',
  mediaType: 'video',
  mimeType: 'video/mp4',
  fileSizeBytes: 52_428_800,
  sha256Hash:
    'a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4' + 'e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2',
  uploadStatus: 'complete',
  processingStatus: 'complete',
  captureTime: '2026-03-15T14:30:00Z',
  clockOffsetSeconds: null,
  clockConfidence: null,
  createdAt: '2026-03-15T16:00:00Z',
  updatedAt: '2026-03-15T16:05:00Z',
};

function renderDetail(asset: Asset = mockAsset): ReturnType<typeof render> {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <AssetDetail asset={asset} caseId="case-1" />
    </QueryClientProvider>,
  );
}

describe('AssetDetail', () => {
  it('renders asset filename', () => {
    renderDetail();
    expect(screen.getByText('protest-footage.mp4')).toBeInTheDocument();
  });

  it('renders media type metadata', () => {
    renderDetail();
    expect(screen.getByText('Media type')).toBeInTheDocument();
    expect(screen.getByText('video')).toBeInTheDocument();
  });

  it('renders MIME type metadata', () => {
    renderDetail();
    expect(screen.getByText('MIME type')).toBeInTheDocument();
    expect(screen.getByText('video/mp4')).toBeInTheDocument();
  });

  it('renders formatted file size', () => {
    renderDetail();
    expect(screen.getByText('File size')).toBeInTheDocument();
    expect(screen.getByText('50.0 MB')).toBeInTheDocument();
  });

  it('shows truncated hash', () => {
    renderDetail();
    expect(screen.getByText('SHA-256')).toBeInTheDocument();
    expect(screen.getByText('a1b2c3d4e5f6a1b2...')).toBeInTheDocument();
  });

  it('shows processing status badge', () => {
    renderDetail();
    const badge = screen.getByTestId('processing-badge');
    expect(badge).toHaveTextContent('complete');
    expect(badge.className).toContain('green');
  });

  it('shows pending processing status', () => {
    renderDetail({
      ...mockAsset,
      processingStatus: 'pending',
    });
    const badge = screen.getByTestId('processing-badge');
    expect(badge).toHaveTextContent('pending');
    expect(badge.className).toContain('yellow');
  });

  it('shows custody chain entries', () => {
    renderDetail();
    expect(screen.getByText('Chain of custody')).toBeInTheDocument();
    expect(screen.getByText('upload')).toBeInTheDocument();
    expect(screen.getByText('process complete')).toBeInTheDocument();
  });

  it('shows custody timeline data-testid', () => {
    renderDetail();
    expect(screen.getByTestId('custody-timeline')).toBeInTheDocument();
  });

  it('shows capture time when available', () => {
    renderDetail();
    expect(screen.getByText('Capture time')).toBeInTheDocument();
  });

  it('hides capture time when null', () => {
    renderDetail({ ...mockAsset, captureTime: null });
    expect(screen.queryByText('Capture time')).not.toBeInTheDocument();
  });

  it('hides clock drift row when both offset and confidence are null', () => {
    renderDetail();
    expect(screen.queryByTestId('clock-drift-row')).not.toBeInTheDocument();
  });

  it('shows clock drift confidence badge when present', () => {
    renderDetail({
      ...mockAsset,
      clockOffsetSeconds: null,
      clockConfidence: 0.1,
    });
    const badge = screen.getByTestId('clock-confidence-badge');
    expect(badge).toHaveTextContent('Low');
    expect(badge.className).toContain('red');
  });

  it('shows formatted offset when user anchor has been applied', () => {
    renderDetail({
      ...mockAsset,
      clockOffsetSeconds: 17,
      clockConfidence: 1.0,
    });
    expect(screen.getByTestId('clock-offset')).toHaveTextContent('+17.0s');
    expect(screen.getByTestId('clock-confidence-badge')).toHaveTextContent(
      'High',
    );
  });

  it('shows download button when url is available', () => {
    renderDetail();
    const link = screen.getByTestId('download-button');
    expect(link).toBeInTheDocument();
    // asset bytes are served cross-origin, so download is forced via an
    // attachment disposition rather than the (ignored) download attr.
    expect(link).toHaveAttribute(
      'href',
      'https://example.com/download/test.mp4?disposition=attachment',
    );
    expect(link).toHaveAttribute('download', 'protest-footage.mp4');
  });
});
