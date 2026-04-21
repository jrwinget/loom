import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  fireEvent,
  render,
  screen,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { ExportWizard } from
  '@/components/export/export-wizard';

const mockMutate = vi.fn();

vi.mock('@/hooks/use-exports', () => ({
  useCreateExport: () => ({
    mutate: mockMutate,
    isPending: false,
  }),
}));

function renderWizard(
  open = true,
): ReturnType<typeof render> {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  const onOpenChange = vi.fn();
  return render(
    <QueryClientProvider client={queryClient}>
      <ExportWizard
        caseId="case-1"
        open={open}
        onOpenChange={onOpenChange}
      />
    </QueryClientProvider>,
  );
}

describe('ExportWizard', () => {
  it('renders step 1 by default', () => {
    renderWizard();
    expect(
      screen.getByTestId('wizard-step-1'),
    ).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText(
        'e.g. Case export 2026-03',
      ),
    ).toBeInTheDocument();
  });

  it('can advance through steps', async () => {
    renderWizard();
    const user = userEvent.setup();

    // step 1: fill name and click next
    const input = screen.getByPlaceholderText(
      'e.g. Case export 2026-03',
    );
    await user.type(input, 'My Export');

    const nextBtn = screen.getByRole('button', {
      name: 'Next',
    });
    await user.click(nextBtn);

    // step 2 visible
    expect(
      screen.getByTestId('wizard-step-2'),
    ).toBeInTheDocument();

    // advance to step 3
    const nextBtn2 = screen.getByRole('button', {
      name: 'Next',
    });
    await user.click(nextBtn2);

    // step 3 visible
    expect(
      screen.getByTestId('wizard-step-3'),
    ).toBeInTheDocument();
  });

  it('submit button calls mutation', async () => {
    renderWizard();
    const user = userEvent.setup();

    // step 1
    await user.type(
      screen.getByPlaceholderText(
        'e.g. Case export 2026-03',
      ),
      'My Export',
    );
    await user.click(
      screen.getByRole('button', { name: 'Next' }),
    );

    // step 2
    await user.click(
      screen.getByRole('button', { name: 'Next' }),
    );

    // step 3 - submit
    const submitBtn = screen.getByTestId(
      'export-submit',
    );
    await user.click(submitBtn);

    expect(mockMutate).toHaveBeenCalledTimes(1);
    expect(mockMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        name: 'My Export',
        format: 'zip',
      }),
      expect.any(Object),
    );
  });
});
