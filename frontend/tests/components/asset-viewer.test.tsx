/// <reference types="@testing-library/jest-dom" />
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AssetViewer } from '@/components/asset/asset-viewer';
import { loadPdf } from '@/lib/pdf';
import type { Asset, MediaType } from '@/types/asset';

vi.mock('@/lib/pdf', () => ({ loadPdf: vi.fn() }));
const mockLoadPdf = vi.mocked(loadPdf);

function fakePdf(numPages: number) {
  return {
    numPages,
    renderPage: vi.fn().mockResolvedValue(undefined),
    destroy: vi.fn(),
  };
}

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

beforeEach(() => {
  mockLoadPdf.mockReset();
});

describe('AssetViewer', () => {
  it('renders a pdf inline with pdf.js (no native object element)', async () => {
    mockLoadPdf.mockResolvedValue(fakePdf(3));
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
    // loading indicator shows synchronously, before the document resolves
    expect(screen.getByText(/Loading PDF/)).toBeInTheDocument();
    expect(await screen.findByText('Page 1 / 3')).toBeInTheDocument();
    expect(screen.getByTestId('pdf-canvas')).toBeInTheDocument();
    expect(container.querySelector('object')).toBeNull();
    expect(mockLoadPdf).toHaveBeenCalledWith(SRC);
  });

  it('pages and zooms through the pdf', async () => {
    mockLoadPdf.mockResolvedValue(fakePdf(2));
    render(
      <AssetViewer
        asset={makeAsset({
          mediaType: 'document',
          mimeType: 'application/pdf',
          originalFilename: 'evidence.pdf',
        })}
        src={SRC}
      />,
    );
    await screen.findByText('Page 1 / 2');

    expect(screen.getByRole('button', { name: 'Prev' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(screen.getByText('Page 2 / 2')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Prev' }));
    expect(screen.getByText('Page 1 / 2')).toBeInTheDocument();

    expect(screen.getByText('120%')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Zoom in'));
    expect(screen.getByText('145%')).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText('Zoom out'));
    expect(screen.getByText('120%')).toBeInTheDocument();
  });

  it('falls back to download when a pdf cannot be rendered', async () => {
    mockLoadPdf.mockRejectedValue(new Error('corrupt'));
    render(
      <AssetViewer
        asset={makeAsset({
          mediaType: 'document',
          mimeType: 'application/pdf',
          originalFilename: 'broken.pdf',
        })}
        src={SRC}
      />,
    );
    expect(await screen.findByText(/render this PDF/)).toBeInTheDocument();
    expect(screen.getByText('Download file')).toHaveAttribute(
      'href',
      `${SRC}&disposition=attachment`,
    );
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

  it('falls back to download when the video codec is unsupported', () => {
    render(
      <AssetViewer
        asset={makeAsset({ mediaType: 'video', mimeType: 'video/mp4' })}
        src={SRC}
      />,
    );
    fireEvent.error(screen.getByTestId('video-element'));
    expect(screen.getByText(/play in this app/)).toBeInTheDocument();
    expect(screen.getByText('Download file')).toHaveAttribute(
      'href',
      `${SRC}&disposition=attachment`,
    );
  });
});
