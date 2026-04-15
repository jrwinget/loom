import { render, screen, fireEvent } from
  '@testing-library/react';
import { QueryClient, QueryClientProvider } from
  '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from
  'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { ConflictsPage } from
  '@/routes/cases/[caseId]/conflicts';
import type { ConflictListResponse } from '@/types/conflict';

vi.mock('@/hooks/use-conflicts', () => ({
  useCaseConflicts: vi.fn(),
}));

// mock the conflict panel to avoid nested hook issues
vi.mock(
  '@/components/timeline/conflict-panel',
  () => ({
    ConflictPanel: (
      { eventTitle, onClose }: {
        eventTitle: string;
        onClose: () => void;
      },
    ) => (
      <div data-testid="conflict-panel">
        <span>{eventTitle}</span>
        <button onClick={onClose}>Close</button>
      </div>
    ),
  }),
);

import { useCaseConflicts } from '@/hooks/use-conflicts';

const mockUseCaseConflicts = vi.mocked(useCaseConflicts);

function makeListResponse(
  overrides: Partial<ConflictListResponse> = {},
): ConflictListResponse {
  return {
    items: [
      {
        eventId: 'event-1',
        eventTitle: 'Arrest at 5th and Main',
        supportingCount: 3,
        contradictingCount: 2,
        resolutionCount: 0,
        isResolved: false,
      },
      {
        eventId: 'event-2',
        eventTitle: 'Officer statement',
        supportingCount: 1,
        contradictingCount: 1,
        resolutionCount: 1,
        isResolved: true,
      },
    ],
    total: 2,
    ...overrides,
  };
}

function renderPage(): void {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/cases/case-1/conflicts']}>
        <Routes>
          <Route
            path="cases/:caseId/conflicts"
            element={<ConflictsPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ConflictsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders conflict list items', () => {
    mockUseCaseConflicts.mockReturnValue({
      data: makeListResponse(),
      isLoading: false,
    } as ReturnType<typeof useCaseConflicts>);

    renderPage();

    expect(
      screen.getByText('Arrest at 5th and Main'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Officer statement'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('3 supports, 2 contradicts'),
    ).toBeInTheDocument();
  });

  it('filter toggle works', () => {
    mockUseCaseConflicts.mockReturnValue({
      data: makeListResponse(),
      isLoading: false,
    } as ReturnType<typeof useCaseConflicts>);

    renderPage();

    const unresolvedBtn = screen.getByTestId(
      'filter-unresolved',
    );
    fireEvent.click(unresolvedBtn);

    // verify the button gets the active styling
    expect(unresolvedBtn.className).toContain('bg-primary');
  });

  it('shows resolution status badges', () => {
    mockUseCaseConflicts.mockReturnValue({
      data: makeListResponse(),
      isLoading: false,
    } as ReturnType<typeof useCaseConflicts>);

    renderPage();

    expect(
      screen.getByTestId('status-badge-unresolved'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('status-badge-resolved'),
    ).toBeInTheDocument();
  });

  it('shows empty state', () => {
    mockUseCaseConflicts.mockReturnValue({
      data: { items: [], total: 0 },
      isLoading: false,
    } as ReturnType<typeof useCaseConflicts>);

    renderPage();

    expect(
      screen.getByText('No conflicts found'),
    ).toBeInTheDocument();
  });
});
