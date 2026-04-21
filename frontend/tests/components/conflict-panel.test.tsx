import { render, screen, fireEvent } from
  '@testing-library/react';
import { QueryClient, QueryClientProvider } from
  '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { ConflictPanel } from
  '@/components/timeline/conflict-panel';
import type { ConflictDetail } from '@/types/conflict';

// mock the hooks
const mockMutate = vi.fn();

vi.mock('@/hooks/use-conflicts', () => ({
  useEventConflicts: vi.fn(),
  useCreateResolution: vi.fn(() => ({
    mutate: mockMutate,
    isPending: false,
  })),
}));

import {
  useEventConflicts,
} from '@/hooks/use-conflicts';

const mockUseEventConflicts = vi.mocked(useEventConflicts);

function makeDetail(
  overrides: Partial<ConflictDetail> = {},
): ConflictDetail {
  return {
    eventId: 'event-1',
    eventTitle: 'Test Event',
    supporting: [
      {
        id: 'ev-1',
        assetId: 'asset-1',
        originalFilename: 'video-001.mp4',
        annotationId: null,
        clipStart: 10,
        clipEnd: 25,
        relationship: 'supports',
        notes: 'Clear footage',
      },
    ],
    contradicting: [
      {
        id: 'ev-2',
        assetId: 'asset-2',
        originalFilename: 'photo-003.jpg',
        annotationId: null,
        clipStart: null,
        clipEnd: null,
        relationship: 'contradicts',
        notes: 'Different angle shows otherwise',
      },
    ],
    resolutions: [],
    ...overrides,
  };
}

function wrapper(
  { children }: { children: React.ReactNode },
): React.ReactElement {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return (
    <QueryClientProvider client={qc}>
      {children}
    </QueryClientProvider>
  );
}

const onClose = vi.fn();

describe('ConflictPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders supporting and contradicting evidence', () => {
    const detail = makeDetail();
    mockUseEventConflicts.mockReturnValue({
      data: detail,
      isLoading: false,
    } as ReturnType<typeof useEventConflicts>);

    render(
      <ConflictPanel
        caseId="case-1"
        eventId="event-1"
        eventTitle="Test Event"
        onClose={onClose}
      />,
      { wrapper },
    );

    expect(
      screen.getByText('Supporting Evidence (1)'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Contradicting Evidence (1)'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('video-001.mp4'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('photo-003.jpg'),
    ).toBeInTheDocument();
  });

  it('submits resolution form', () => {
    const detail = makeDetail();
    mockUseEventConflicts.mockReturnValue({
      data: detail,
      isLoading: false,
    } as ReturnType<typeof useEventConflicts>);

    render(
      <ConflictPanel
        caseId="case-1"
        eventId="event-1"
        eventTitle="Test Event"
        onClose={onClose}
      />,
      { wrapper },
    );

    const notesInput = screen.getByTestId(
      'resolution-notes',
    );
    fireEvent.change(notesInput, {
      target: { value: 'Accepted after review' },
    });

    const submitBtn = screen.getByText('Submit Resolution');
    fireEvent.click(submitBtn);

    expect(mockMutate).toHaveBeenCalledWith(
      {
        resolutionType: 'Accepted Supporting',
        notes: 'Accepted after review',
      },
      expect.any(Object),
    );
  });

  it('shows existing resolutions', () => {
    const detail = makeDetail({
      resolutions: [
        {
          id: 'res-1',
          eventId: 'event-1',
          resolutionType: 'Noted',
          notes: 'Under review',
          resolvedBy: 'user-1',
          createdAt: '2026-02-01T12:00:00Z',
        },
      ],
    });
    mockUseEventConflicts.mockReturnValue({
      data: detail,
      isLoading: false,
    } as ReturnType<typeof useEventConflicts>);

    render(
      <ConflictPanel
        caseId="case-1"
        eventId="event-1"
        eventTitle="Test Event"
        onClose={onClose}
      />,
      { wrapper },
    );

    expect(
      screen.getByText('Resolutions (1)'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('resolution-res-1'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Under review'),
    ).toBeInTheDocument();
  });

  it('shows empty state when no contradictions', () => {
    const detail = makeDetail({
      supporting: [],
      contradicting: [],
    });
    mockUseEventConflicts.mockReturnValue({
      data: detail,
      isLoading: false,
    } as ReturnType<typeof useEventConflicts>);

    render(
      <ConflictPanel
        caseId="case-1"
        eventId="event-1"
        eventTitle="Test Event"
        onClose={onClose}
      />,
      { wrapper },
    );

    expect(
      screen.getByText('No supporting evidence'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('No contradicting evidence'),
    ).toBeInTheDocument();
  });
});
