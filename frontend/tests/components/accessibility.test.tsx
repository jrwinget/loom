import { render, screen } from '@testing-library/react';
import {
  QueryClient,
  QueryClientProvider,
} from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { axe } from 'jest-axe';
import { CaseCard } from '@/components/case/case-card';
import { Shell } from '@/components/layout/shell';
import { ReviewWorkspace } from
  '@/components/review/review-workspace';
import { ErrorFallback } from
  '@/components/layout/error-boundary';
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

const mockNavigate = vi.fn();

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

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

describe('Accessibility (axe)', () => {
  it('CaseCard has no violations', async () => {
    const { container } = render(
      <MemoryRouter>
        <CaseCard
          id="case-1"
          name="Test Case"
          description="Description"
          status="active"
          assetCount={5}
          eventCount={12}
          createdAt="2026-01-15T10:00:00Z"
        />
      </MemoryRouter>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it('Shell layout has no violations', async () => {
    const qc = makeQueryClient();
    const { container } = render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <Shell />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // verify skip link and landmark structure
    expect(
      screen.getByText('Skip to main content'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('main-content'),
    ).toHaveAttribute('id', 'main-content');

    expect(await axe(container)).toHaveNoViolations();
  });

  it('ReviewWorkspace has no violations', async () => {
    const qc = makeQueryClient();
    const { container } = render(
      <QueryClientProvider client={qc}>
        <ReviewWorkspace
          caseId="case-1"
          asset={makeAsset()}
          assetSrc="/test.mp4"
          segments={[]}
          scenes={[]}
        />
      </QueryClientProvider>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it('ErrorFallback has no violations', async () => {
    const { container } = render(
      <ErrorFallback
        error={new Error('test error')}
        onReset={() => {}}
      />,
    );

    // verify alert role and aria-live
    const alert = screen.getByRole('alert');
    expect(alert).toHaveAttribute(
      'aria-live',
      'assertive',
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});
