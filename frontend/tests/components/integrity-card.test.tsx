import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { IntegrityCard } from '@/components/case/integrity-card';

const mockMutate = vi.fn();
let mockState: {
  mutate: typeof mockMutate;
  isPending: boolean;
  data: unknown;
};

vi.mock('@/hooks/use-integrity', () => ({
  useVerifyCase: () => mockState,
}));

function renderCard(): void {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <IntegrityCard caseId="case-1" />
    </QueryClientProvider>,
  );
}

describe('IntegrityCard', () => {
  beforeEach(() => {
    mockMutate.mockReset();
    mockState = { mutate: mockMutate, isPending: false, data: undefined };
  });

  it('runs verification when the button is clicked', async () => {
    renderCard();
    const user = userEvent.setup();

    await user.click(screen.getByTestId('verify-case-btn'));

    expect(mockMutate).toHaveBeenCalledTimes(1);
  });

  it('shows a pending label while verifying', () => {
    mockState = { mutate: mockMutate, isPending: true, data: undefined };
    renderCard();

    expect(screen.getByTestId('verify-case-btn')).toBeDisabled();
    expect(screen.getByText('Verifying…')).toBeInTheDocument();
  });

  it('summarizes a clean run without a failure list', async () => {
    mockState = {
      mutate: mockMutate,
      isPending: false,
      data: {
        caseId: 'case-1',
        totalAssets: 3,
        passedCount: 3,
        failedCount: 0,
        results: [],
        verifiedAt: '2026-07-24T12:00:00Z',
      },
    };
    renderCard();

    await waitFor(() => {
      expect(screen.getByTestId('verify-case-summary')).toHaveTextContent(
        '3 of 3 verified',
      );
    });
    expect(
      screen.queryByTestId('verify-case-failures'),
    ).not.toBeInTheDocument();
  });

  it('names every asset that failed verification', async () => {
    mockState = {
      mutate: mockMutate,
      isPending: false,
      data: {
        caseId: 'case-1',
        totalAssets: 2,
        passedCount: 1,
        failedCount: 1,
        results: [
          { assetId: 'a1', storageKey: 'case/ok.mp4', passed: true },
          { assetId: 'a2', storageKey: 'case/bad.mp4', passed: false },
        ],
        verifiedAt: '2026-07-24T12:00:00Z',
      },
    };
    renderCard();

    const failures = await screen.findByTestId('verify-case-failures');
    expect(failures).toHaveTextContent('FAILED: case/bad.mp4');
    expect(failures).not.toHaveTextContent('ok.mp4');
  });
});
