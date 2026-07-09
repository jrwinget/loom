import { fireEvent, render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { ReviewWorkspace } from '@/components/review/review-workspace';
import type { Asset } from '@/types/asset';

// mock keyboard shortcut
vi.mock('@/hooks/use-keyboard', () => ({
  useKeyboardShortcut: vi.fn(),
}));

// mock search hook
vi.mock('@/hooks/use-search', () => ({
  useSearch: () => ({
    data: { results: [], total: 0, facets: {} },
    isLoading: false,
  }),
}));

function makeAsset(overrides: Partial<Asset> = {}): Asset {
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
    clockOffsetSeconds: null,
    clockConfidence: null,
    createdAt: '2026-01-15T10:00:00Z',
    updatedAt: '2026-01-15T10:05:00Z',
    ...overrides,
  };
}

function renderWithQuery(ui: React.ReactElement): ReturnType<typeof render> {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

describe('ReviewWorkspace', () => {
  it('renders all panels', () => {
    renderWithQuery(
      <ReviewWorkspace
        caseId="case-1"
        asset={makeAsset()}
        assetSrc="/test.mp4"
        segments={[]}
        scenes={[]}
      />,
    );

    expect(screen.getByTestId('review-workspace')).toBeInTheDocument();
    expect(screen.getByTestId('panel-video')).toBeInTheDocument();
    expect(screen.getByTestId('panel-transcript')).toBeInTheDocument();
    expect(screen.getByTestId('panel-right')).toBeInTheDocument();
  });

  it('renders search bar', () => {
    renderWithQuery(
      <ReviewWorkspace
        caseId="case-1"
        asset={makeAsset()}
        assetSrc="/test.mp4"
        segments={[]}
        scenes={[]}
      />,
    );

    expect(screen.getByTestId('search-bar')).toBeInTheDocument();
  });

  it('renders scene strip', () => {
    renderWithQuery(
      <ReviewWorkspace
        caseId="case-1"
        asset={makeAsset()}
        assetSrc="/test.mp4"
        segments={[]}
        scenes={[]}
      />,
    );

    expect(screen.getByTestId('scene-strip')).toBeInTheDocument();
  });

  it('renders transcript panel with segments', () => {
    renderWithQuery(
      <ReviewWorkspace
        caseId="case-1"
        asset={makeAsset()}
        assetSrc="/test.mp4"
        segments={[
          {
            id: 'seg-1',
            assetId: 'asset-1',
            speakerLabel: null,
            startTime: 0,
            endTime: 5,
            text: 'Hello there',
            confidence: 0.9,
            language: 'en',
          },
        ]}
        scenes={[]}
      />,
    );

    expect(screen.getByText('Hello there')).toBeInTheDocument();
  });

  it('highlights the transcript from the video timeupdate event', () => {
    renderWithQuery(
      <ReviewWorkspace
        caseId="case-1"
        asset={makeAsset()}
        assetSrc="/test.mp4"
        segments={[
          {
            id: 'seg-1',
            assetId: 'asset-1',
            speakerLabel: null,
            startTime: 0,
            endTime: 5,
            text: 'Hello there',
            confidence: 0.9,
            language: 'en',
          },
          {
            id: 'seg-2',
            assetId: 'asset-1',
            speakerLabel: null,
            startTime: 5,
            endTime: 10,
            text: 'Second segment',
            confidence: 0.9,
            language: 'en',
          },
        ]}
        scenes={[]}
      />,
    );

    const video = screen.getByTestId('video-element') as HTMLVideoElement;
    video.currentTime = 6;
    fireEvent.timeUpdate(video);

    expect(screen.getByTestId('segment-seg-2')).toHaveAttribute(
      'data-active',
      'true',
    );
    expect(screen.getByTestId('segment-seg-1')).toHaveAttribute(
      'data-active',
      'false',
    );
  });

  it('seeks the video when a transcript segment is clicked', () => {
    renderWithQuery(
      <ReviewWorkspace
        caseId="case-1"
        asset={makeAsset()}
        assetSrc="/test.mp4"
        segments={[
          {
            id: 'seg-1',
            assetId: 'asset-1',
            speakerLabel: null,
            startTime: 4,
            endTime: 9,
            text: 'Hello there',
            confidence: 0.9,
            language: 'en',
          },
        ]}
        scenes={[]}
      />,
    );

    fireEvent.click(screen.getByTestId('segment-seg-1'));

    const video = screen.getByTestId('video-element') as HTMLVideoElement;
    expect(video.currentTime).toBe(4);
  });
});
