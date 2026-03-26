import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { AssetGrid } from
  '@/components/asset/asset-grid';
import type { Asset } from '@/types/asset';

function makeAsset(
  overrides: Partial<Asset> = {},
): Asset {
  return {
    id: 'asset-1',
    caseId: 'case-1',
    originalFilename: 'evidence.mp4',
    storageKey: 'abc/evidence.mp4',
    mediaType: 'video',
    mimeType: 'video/mp4',
    fileSizeBytes: 1_048_576,
    sha256Hash: 'a'.repeat(64),
    uploadStatus: 'complete',
    processingStatus: 'complete',
    captureTime: null,
    createdAt: '2026-01-15T10:00:00Z',
    updatedAt: '2026-01-15T10:05:00Z',
    ...overrides,
  };
}

const onSelect = vi.fn();

describe('AssetGrid', () => {
  it('renders correct number of asset cards', () => {
    const assets = [
      makeAsset({ id: 'a1' }),
      makeAsset({ id: 'a2' }),
      makeAsset({ id: 'a3' }),
    ];
    render(
      <MemoryRouter>
        <AssetGrid
          assets={assets}
          onSelect={onSelect}
        />
      </MemoryRouter>,
    );
    expect(
      screen.getByTestId('asset-card-a1'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('asset-card-a2'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('asset-card-a3'),
    ).toBeInTheDocument();
  });

  it('shows loading skeleton', () => {
    render(
      <AssetGrid
        assets={[]}
        loading
        onSelect={onSelect}
      />,
    );
    const skeletons = screen.getAllByTestId(
      'skeleton-card',
    );
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('shows empty state', () => {
    render(
      <AssetGrid
        assets={[]}
        onSelect={onSelect}
      />,
    );
    expect(
      screen.getByText('No assets uploaded yet'),
    ).toBeInTheDocument();
  });

  it('renders media type badges correctly', () => {
    const assets = [
      makeAsset({
        id: 'v1',
        mediaType: 'video',
      }),
      makeAsset({
        id: 'i1',
        mediaType: 'image',
      }),
      makeAsset({
        id: 'a1',
        mediaType: 'audio',
      }),
    ];
    render(
      <MemoryRouter>
        <AssetGrid
          assets={assets}
          onSelect={onSelect}
        />
      </MemoryRouter>,
    );
    const badges = screen.getAllByTestId(
      'media-type-badge',
    );
    expect(badges).toHaveLength(3);
    expect(badges[0]).toHaveTextContent('video');
    expect(badges[1]).toHaveTextContent('image');
    expect(badges[2]).toHaveTextContent('audio');
  });
});
