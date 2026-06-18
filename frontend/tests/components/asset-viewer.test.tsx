/// <reference types="@testing-library/jest-dom" />
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { AssetViewer } from '@/components/asset/asset-viewer';
import type { Asset, MediaType } from '@/types/asset';

function makeAsset(over: {
  mediaType: MediaType;
  mimeType: string;
  originalFilename?: string;
}): Asset {
  return {
    id: 'asset-1',
    caseId: 'case-1',
    originalFilename: over.originalFilename ?? 'file',
    storageKey: 'k',
    mediaType: over.mediaType,
    mimeType: over.mimeType,
    fileSizeBytes: 10,
    sha256Hash: 'abc',
    uploadStatus: 'complete',
    processingStatus: 'complete',
    captureTime: null,
    clockOffsetSeconds: null,
    clockConfidence: null,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
  };
}

const SRC = 'http://127.0.0.1:8000/api/v1/storage/object/b/k?sig=1';

describe('AssetViewer', () => {
  it('renders an inline pdf object for application/pdf documents', () => {
    const { container } = render(
      <AssetViewer
        asset={makeAsset({
          mediaType: 'document',
          mimeType: 'application/pdf',
          originalFilename: 'evidence.pdf',
        })}
        src={SRC}
      />,
    );
    const obj = container.querySelector('object[type="application/pdf"]');
    expect(obj).not.toBeNull();
    expect(obj).toHaveAttribute('data', SRC);
  });

  it('falls back to an attachment download for non-pdf documents', () => {
    render(
      <AssetViewer
        asset={makeAsset({ mediaType: 'document', mimeType: 'text/plain' })}
        src={SRC}
      />,
    );
    expect(screen.getByText('Preview not available')).toBeInTheDocument();
    expect(screen.getByText('Download file')).toHaveAttribute(
      'href',
      `${SRC}&disposition=attachment`,
    );
  });

  it('plays a video directly from the served src', () => {
    render(
      <AssetViewer
        asset={makeAsset({ mediaType: 'video', mimeType: 'video/mp4' })}
        src={SRC}
      />,
    );
    expect(screen.getByTestId('video-element')).toHaveAttribute('src', SRC);
  });
});
