/// <reference types="@testing-library/jest-dom" />
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ReviewPage } from '@/routes/cases/[caseId]/review';
import type { Capabilities } from '@/hooks/use-capabilities';

const { capabilitiesData } = vi.hoisted(() => ({
  capabilitiesData: { current: undefined as Capabilities | undefined },
}));

vi.mock('@/hooks/use-capabilities', () => ({
  useCapabilities: () => ({ data: capabilitiesData.current }),
}));

vi.mock('@/hooks/use-assets', () => ({
  useAsset: () => ({
    data: {
      id: 'asset-1',
      caseId: 'case-1',
      originalFilename: 'clip.mp4',
      storageKey: 'k',
      mediaType: 'video',
      mimeType: 'video/mp4',
      fileSizeBytes: 10,
      sha256Hash: 'a'.repeat(64),
      uploadStatus: 'complete',
      processingStatus: 'complete',
      captureTime: null,
      clockOffsetSeconds: null,
      clockConfidence: null,
      createdAt: '2026-01-01T00:00:00Z',
      updatedAt: '2026-01-01T00:00:00Z',
    },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useAssetDownloadUrl: () => ({ data: 'http://example.test/clip.mp4' }),
}));

vi.mock('@/hooks/use-transcript', () => ({
  useTranscript: () => ({
    data: { segments: [] },
    isLoading: false,
    isError: false,
  }),
  useStartTranscription: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock('@/hooks/use-scenes', () => ({
  useScenes: () => ({ data: [], isLoading: false, isError: false }),
  useStartSceneDetection: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock('@/hooks/use-search', () => ({
  useSearch: () => ({
    data: { results: [], total: 0, facets: {} },
    isLoading: false,
  }),
}));

vi.mock('@/hooks/use-keyboard', () => ({
  useKeyboardShortcut: vi.fn(),
}));

function engines(
  over: Partial<Capabilities['engines']>,
): Capabilities['engines'] {
  const available = { status: 'available', remedy: null, version: null };
  return {
    transcriptionLocal: available,
    transcriptionCloud: available,
    ocr: available,
    sceneDetection: available,
    mediaPipeline: available,
    diarization: available,
    ...over,
  } as Capabilities['engines'];
}

function renderReview(): ReturnType<typeof render> {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/cases/case-1/review/asset-1']}>
        <Routes>
          <Route
            path="/cases/:caseId/review/:assetId"
            element={<ReviewPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ReviewPage engine gating', () => {
  beforeEach(() => {
    capabilitiesData.current = undefined;
  });

  it('leaves actions enabled while capabilities are loading', () => {
    renderReview();
    expect(screen.getByTestId('start-transcription')).not.toBeDisabled();
    expect(screen.getByTestId('start-scene-detection')).not.toBeDisabled();
  });

  it('disables transcription with a remedy when no engine can run it', () => {
    capabilitiesData.current = {
      profile: 'lite',
      engines: engines({
        transcriptionLocal: {
          status: 'missing',
          remedy: 'use cloud transcription (Settings → AI)',
          version: null,
        },
        transcriptionCloud: {
          status: 'missing',
          remedy: null,
          version: null,
        },
      }),
    };
    renderReview();
    const btn = screen.getByTestId('start-transcription');
    expect(btn).toBeDisabled();
    expect(btn).toHaveAttribute(
      'title',
      'use cloud transcription (Settings → AI)',
    );
  });

  it('keeps transcription enabled when only the cloud path exists', () => {
    capabilitiesData.current = {
      profile: 'lite',
      engines: engines({
        transcriptionLocal: {
          status: 'missing',
          remedy: 'install the ai extra',
          version: null,
        },
      }),
    };
    renderReview();
    expect(screen.getByTestId('start-transcription')).not.toBeDisabled();
  });

  it('disables scene detection when its engine is missing', () => {
    capabilitiesData.current = {
      profile: 'lite',
      engines: engines({
        sceneDetection: {
          status: 'missing',
          remedy: 'install the ai extra',
          version: null,
        },
      }),
    };
    renderReview();
    expect(screen.getByTestId('start-scene-detection')).toBeDisabled();
  });
});
