import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import {
  QueryClient,
  QueryClientProvider,
} from '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { UrlIngestForm } from '@/components/asset/url-ingest-form';

const mockMutate = vi.fn();

vi.mock('@/hooks/use-ingest-from-url', () => ({
  useIngestFromUrl: () => ({
    mutateAsync: mockMutate,
  }),
}));

function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function renderForm(): ReturnType<typeof render> {
  const qc = makeQueryClient();
  return render(
    <QueryClientProvider client={qc}>
      <UrlIngestForm caseId="case-1" />
    </QueryClientProvider>,
  );
}

describe('UrlIngestForm', () => {
  it('renders textarea and submit button', () => {
    renderForm();
    expect(
      screen.getByTestId('url-ingest-textarea'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('url-ingest-submit'),
    ).toBeInTheDocument();
  });

  it('disables submit when textarea empty', () => {
    renderForm();
    expect(
      screen.getByTestId('url-ingest-submit'),
    ).toBeDisabled();
  });

  it('submits one mutation per URL and reports queued', async () => {
    mockMutate.mockReset();
    mockMutate.mockResolvedValue({
      asset_id: 'asset-1',
      workflow_id: 'url-ingest-asset-1',
      status: 'queued',
    });

    renderForm();
    const user = userEvent.setup();
    const textarea = screen.getByTestId('url-ingest-textarea');
    await user.type(
      textarea,
      'https://example.com/one.mp4\nhttps://example.com/two.mp4',
    );
    await user.click(screen.getByTestId('url-ingest-submit'));

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledTimes(2);
    });

    const statuses = await screen.findAllByTestId(
      'url-entry-status',
    );
    expect(statuses).toHaveLength(2);
    statuses.forEach((s) => {
      expect(s.textContent).toBe('Queued');
    });
  });

  it('shows error status when mutation fails', async () => {
    mockMutate.mockReset();
    mockMutate.mockRejectedValueOnce(
      new Error('workflow service unavailable'),
    );

    renderForm();
    const user = userEvent.setup();
    await user.type(
      screen.getByTestId('url-ingest-textarea'),
      'https://example.com/bad.mp4',
    );
    await user.click(screen.getByTestId('url-ingest-submit'));

    await waitFor(() => {
      expect(
        screen.getByTestId('url-entry-status'),
      ).toHaveTextContent('Error');
    });
    expect(
      screen.getByTestId('url-entry-error'),
    ).toHaveTextContent('workflow service unavailable');
  });
});
