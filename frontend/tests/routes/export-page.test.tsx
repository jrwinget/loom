import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ExportPage } from '@/routes/cases/[caseId]/export';

const { mockDownload } = vi.hoisted(() => ({
  mockDownload: vi.fn(),
}));

const completeExport = {
  id: 'exp-1',
  caseId: 'case-1',
  name: 'Court Bundle',
  format: 'court_bundle',
  storageKey: 'exports/exp-1.zip',
  sha256Hash: 'abc',
  downloadUrl: null,
  status: 'complete',
  createdBy: 'user-1',
  createdAt: '2026-01-01T00:00:00Z',
};

vi.mock('@/hooks/use-exports', () => ({
  useExports: () => ({
    data: { items: [completeExport], total: 1 },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useCreateExport: () => ({ mutate: vi.fn(), isPending: false }),
  useDownloadExport: () => ({
    mutate: mockDownload,
    isPending: false,
    variables: undefined,
  }),
}));

function renderPage(): ReturnType<typeof render> {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/cases/case-1/export']}>
        <Routes>
          <Route path="/cases/:caseId/export" element={<ExportPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ExportPage download', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('requests a fresh download url instead of linking the raw key', async () => {
    renderPage();
    const user = userEvent.setup();

    const btn = screen.getByTestId('export-download-exp-1');
    await user.click(btn);

    expect(mockDownload).toHaveBeenCalledWith('exp-1');
    // no anchor pointing at the raw storage key
    expect(document.querySelector('a[href*="exports/exp-1.zip"]')).toBeNull();
  });
});
