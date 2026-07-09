/// <reference types="@testing-library/jest-dom" />
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { createElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  // keep the real ApiClientError so the hook's `instanceof` 404 check
  // works; only the network call is stubbed
  return { ...actual, apiClient: { get: vi.fn() } };
});

import { AssetViewer } from '@/components/asset/asset-viewer';
import { ApiClientError, apiClient } from '@/lib/api-client';
import type { Asset } from '@/types/asset';

const mockedGet = vi.mocked(apiClient.get);

const AUDIO: Asset = {
  id: 'asset-1',
  caseId: 'case-1',
  originalFilename: 'call.mp3',
  storageKey: 'k',
  mediaType: 'audio',
  mimeType: 'audio/mpeg',
  metadataExtracted: null,
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

const SRC = 'http://127.0.0.1:8000/api/v1/storage/object/b/k?sig=1';

const CAPS_OK = {
  profile: 'lite',
  engines: {
    mediaPipeline: { status: 'available', remedy: null, version: '6' },
  },
};
const CAPS_MISSING = {
  profile: 'lite',
  engines: {
    mediaPipeline: {
      status: 'missing',
      remedy: 'install ffmpeg and make sure it is on PATH',
      version: null,
    },
  },
};

function wrapper(): React.FC<{ children: React.ReactNode }> {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }) =>
    createElement(QueryClientProvider, { client: qc }, children);
}

function mockRoutes(
  waveform: () => Promise<unknown>,
  caps: unknown = CAPS_OK,
): void {
  mockedGet.mockImplementation((path: string) => {
    if (path.endsWith('/waveform')) return waveform() as never;
    if (path === '/capabilities') return Promise.resolve(caps) as never;
    return Promise.reject(new Error(`unexpected path ${path}`)) as never;
  });
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('AudioWaveform', () => {
  it('renders the canvas when real peaks are returned', async () => {
    mockRoutes(() => Promise.resolve({ peaks: [0.1, 0.5, 1, 0.2] }));
    render(<AssetViewer asset={AUDIO} src={SRC} />, { wrapper: wrapper() });
    expect(await screen.findByTestId('audio-waveform')).toBeInTheDocument();
    expect(
      screen.queryByTestId('waveform-unavailable'),
    ).not.toBeInTheDocument();
  });

  it('shows an honest unavailable state on a 404 (no fake bars)', async () => {
    mockRoutes(() => Promise.reject(new ApiClientError(404, 'not found')));
    render(<AssetViewer asset={AUDIO} src={SRC} />, { wrapper: wrapper() });
    expect(
      await screen.findByTestId('waveform-unavailable'),
    ).toHaveTextContent('Waveform unavailable');
    expect(screen.queryByTestId('audio-waveform')).not.toBeInTheDocument();
  });

  it('surfaces the ffmpeg remedy when the media engine is missing', async () => {
    mockRoutes(
      () => Promise.reject(new ApiClientError(404, 'not found')),
      CAPS_MISSING,
    );
    render(<AssetViewer asset={AUDIO} src={SRC} />, { wrapper: wrapper() });
    await screen.findByTestId('waveform-unavailable');
    expect(screen.getByText(/install ffmpeg/)).toBeInTheDocument();
  });
});
