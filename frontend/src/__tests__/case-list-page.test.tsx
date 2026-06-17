/// <reference types="@testing-library/jest-dom" />
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CaseListPage } from '@/routes/cases';

vi.mock('@/lib/api-client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

import { apiClient } from '@/lib/api-client';

const mockedGet = vi.mocked(apiClient.get);

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <CaseListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('CaseListPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // regression: GET /cases returns a {items,total} envelope. the page
  // must unwrap it and show the empty state -- the old code treated the
  // envelope as the array and crashed on `.map` with zero cases.
  it('shows the empty state for an empty case-list envelope', async () => {
    mockedGet.mockResolvedValueOnce({ items: [], total: 0 });

    renderPage();

    expect(await screen.findByTestId('empty-state')).toBeInTheDocument();
    expect(screen.getByText('No cases yet')).toBeInTheDocument();
  });

  // regression: description is nullable on the wire; the card must not
  // dereference it.
  it('renders a case with a null description without crashing', async () => {
    mockedGet.mockResolvedValueOnce({
      items: [
        {
          id: 'case-1',
          name: 'Protest 5/1',
          description: null,
          status: 'active',
          assetCount: 0,
          eventCount: 0,
          createdAt: '2026-05-01T00:00:00Z',
        },
      ],
      total: 1,
    });

    renderPage();

    expect(await screen.findByText('Protest 5/1')).toBeInTheDocument();
    expect(screen.getByTestId('case-card-case-1')).toBeInTheDocument();
  });
});
