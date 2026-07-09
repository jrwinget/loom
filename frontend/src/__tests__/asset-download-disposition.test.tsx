/// <reference types="@testing-library/jest-dom" />
import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

// guards #322: the download anchor must use the server-provided url
// verbatim. appending an unsigned ?disposition=attachment param breaks
// minio's sigv4 verification (403); the content-disposition is now
// signed into the url by the backend instead.

const PRESIGNED_URL =
  'https://minio.test/loom-originals/c/a/report.pdf' +
  '?X-Amz-Signature=deadbeef' +
  '&response-content-disposition=attachment%3B%20filename%3D%22report.pdf%22';

vi.mock('@/hooks/use-assets', () => ({
  useAssetDownloadUrl: () => ({ data: PRESIGNED_URL }),
}));

vi.mock('@/hooks/use-custody', () => ({
  useAssetCustody: () => ({ data: undefined, isLoading: false }),
}));

import { AssetDetail } from '@/components/asset/asset-detail';
import type { Asset } from '@/types/asset';

const asset = {
  id: 'a',
  caseId: 'c',
  originalFilename: 'report.pdf',
  storageKey: 'c/a/report.pdf',
  mediaType: 'document',
  mimeType: 'application/pdf',
  fileSizeBytes: 1024,
  sha256Hash: 'a'.repeat(64),
  uploadStatus: 'complete',
  processingStatus: 'complete',
  captureTime: null,
  clockOffsetSeconds: null,
  clockConfidence: null,
  createdAt: '2026-07-09T00:00:00Z',
  updatedAt: '2026-07-09T00:00:00Z',
} as unknown as Asset;

describe('AssetDetail download anchor', () => {
  it('links to the signed url without appending a disposition param', () => {
    const { getByTestId } = render(<AssetDetail asset={asset} caseId="c" />);
    const href = getByTestId('download-button').getAttribute('href');
    // exact match proves nothing was appended after the signed query.
    expect(href).toBe(PRESIGNED_URL);
  });
});
