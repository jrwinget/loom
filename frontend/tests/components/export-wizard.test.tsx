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

  async function fillNameAndAdvance(
    user: ReturnType<typeof userEvent.setup>,
    format?: string,
  ): Promise<void> {
    await user.type(
      screen.getByPlaceholderText('e.g. Case export 2026-03'),
      'My Export',
    );
    if (format) {
      fireEvent.change(screen.getByRole('combobox'), {
        target: { value: format },
      });
    }
    await user.click(screen.getByRole('button', { name: 'Next' }));
  }

  it('zip defaults to including the analysis layer', async () => {
    renderWizard();
    const user = userEvent.setup();
    await fillNameAndAdvance(user);

    expect(screen.getByTestId('include-analysis')).toBeChecked();
    expect(
      screen.getByTestId('work-product-warning'),
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Next' }));
    await user.click(screen.getByTestId('export-submit'));

    expect(mockMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        format: 'zip',
        include_analysis: true,
        include_originals: false,
      }),
      expect.any(Object),
    );
  });

  it('court bundle defaults to an evidence-only production', async () => {
    renderWizard();
    const user = userEvent.setup();
    await fillNameAndAdvance(user, 'court_bundle');

    expect(screen.getByTestId('include-analysis')).not.toBeChecked();
    expect(
      screen.queryByTestId('work-product-warning'),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/Evidence-only production/),
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Next' }));
    await user.click(screen.getByTestId('export-submit'));

    expect(mockMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        format: 'court_bundle',
        include_analysis: false,
      }),
      expect.any(Object),
    );
  });

  it('opting analysis into a court bundle shows the warning', async () => {
    renderWizard();
    const user = userEvent.setup();
    await fillNameAndAdvance(user, 'court_bundle');

    await user.click(screen.getByTestId('include-analysis'));
    expect(
      screen.getByTestId('work-product-warning'),
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Next' }));
    expect(
      screen.getByText('Included (work product)'),
    ).toBeInTheDocument();
    await user.click(screen.getByTestId('export-submit'));

    expect(mockMutate).toHaveBeenCalledWith(
      expect.objectContaining({ include_analysis: true }),
      expect.any(Object),
    );
  });

  it('hides layer controls for formats without a choice', async () => {
    renderWizard();
    const user = userEvent.setup();
    await fillNameAndAdvance(user, 'portable_bundle');

    expect(
      screen.queryByTestId('layer-controls'),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText(/always contain the whole case/),
    ).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Next' }));
    await user.click(screen.getByTestId('export-submit'));

    const payload = mockMutate.mock.calls.at(-1)?.[0] as Record<
      string,
      unknown
    >;
    expect(payload).not.toHaveProperty('include_analysis');
    expect(payload).not.toHaveProperty('include_originals');
  });
});
