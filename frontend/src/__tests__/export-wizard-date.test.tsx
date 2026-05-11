/// <reference types="@testing-library/jest-dom" />
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { ExportWizard } from '@/components/export/export-wizard';

vi.mock('@/hooks/use-exports', () => ({
  useCreateExport: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
}));

function wrap(ui: ReactNode): ReactNode {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={client}>{ui}</QueryClientProvider>;
}

describe('ExportWizard date range validation', () => {
  it('shows an error and disables Next when end precedes start', async () => {
    const user = userEvent.setup();
    render(
      wrap(
        <ExportWizard caseId="case-1" open onOpenChange={vi.fn()} />,
      ),
    );

    // step 1 → name + format. fill name and advance to step 2.
    await user.type(screen.getByPlaceholderText(/Case export/i), 'My export');
    await user.click(screen.getByRole('button', { name: /next/i }));

    // step 2 → date inputs. start after end should surface an error.
    await user.type(screen.getByLabelText(/Date Range Start/i), '2026-05-10');
    await user.type(screen.getByLabelText(/Date Range End/i), '2026-05-01');

    expect(screen.getByTestId('date-range-error')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /next/i })).toBeDisabled();
  });
});
