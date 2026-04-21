import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ReportBuilder } from '@/components/export/report-builder';

// mock hooks
vi.mock('@/hooks/use-exports', () => ({
  useCreateExport: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isSuccess: false,
  })),
}));

vi.mock('@/hooks/use-timeline', () => ({
  useTimelineEvents: vi.fn(() => ({
    data: {
      items: [
        {
          id: 'e1',
          title: 'Event One',
          status: 'accepted',
        },
        {
          id: 'e2',
          title: 'Event Two',
          status: 'draft',
        },
      ],
      total: 2,
    },
    isLoading: false,
  })),
}));

import { useCreateExport } from '@/hooks/use-exports';

const mockMutate = vi.fn();
const mockUseCreateExport = vi.mocked(useCreateExport);

function renderWithProviders(ui: React.ReactElement): void {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      {ui}
    </QueryClientProvider>,
  );
}

describe('ReportBuilder', () => {
  it('renders the form', () => {
    renderWithProviders(<ReportBuilder caseId="case-1" />);

    expect(
      screen.getByTestId('report-builder'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('report-date-start'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('report-date-end'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('report-summary'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('generate-report-btn'),
    ).toBeInTheDocument();
  });

  it('submits and creates export mutation', async () => {
    mockUseCreateExport.mockReturnValue({
      mutate: mockMutate,
      isPending: false,
      isSuccess: false,
    } as unknown as ReturnType<typeof useCreateExport>);

    renderWithProviders(<ReportBuilder caseId="case-1" />);

    const user = userEvent.setup();
    const btn = screen.getByTestId('generate-report-btn');
    await user.click(btn);

    expect(mockMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        format: 'pdf_report',
      }),
    );
  });

  it('shows section toggles', () => {
    renderWithProviders(<ReportBuilder caseId="case-1" />);

    expect(screen.getByText('Evidence')).toBeInTheDocument();
    expect(
      screen.getByText('Contradictions'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Chain of Custody'),
    ).toBeInTheDocument();
  });
});
