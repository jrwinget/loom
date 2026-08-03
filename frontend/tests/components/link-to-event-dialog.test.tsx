import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { LinkToEventDialog } from '@/components/review/link-to-event-dialog';

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

const eventsResponse = {
  items: [
    {
      id: 'evt-1',
      caseId: 'case-1',
      title: 'Protest at City Hall',
      status: 'draft',
    },
    {
      id: 'evt-2',
      caseId: 'case-1',
      title: 'Arrest on Main St',
      status: 'confirmed',
    },
  ],
  total: 2,
};

interface RenderOptions {
  clipStart?: number;
  clipEnd?: number;
  onClose?: ReturnType<typeof vi.fn>;
}

function renderDialog(options: RenderOptions = {}): {
  onClose: ReturnType<typeof vi.fn>;
} {
  const onClose = options.onClose ?? vi.fn();
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={qc}>
      <LinkToEventDialog
        caseId="case-1"
        assetId="asset-1"
        clipStart={options.clipStart}
        clipEnd={options.clipEnd}
        onClose={onClose}
      />
    </QueryClientProvider>,
  );
  return { onClose };
}

// the select element exists before the events query resolves, so
// findByLabelText alone can return it empty; wait for the options
async function findLoadedEventSelect(): Promise<HTMLSelectElement> {
  const select = await screen.findByLabelText<HTMLSelectElement>('Event');
  await waitFor(() =>
    expect(select.options.length).toBe(eventsResponse.items.length),
  );
  return select;
}

describe('LinkToEventDialog', () => {
  beforeEach(async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.get).mockResolvedValue(eventsResponse);
  });

  it('lists the case events in the picker', async () => {
    renderDialog();

    const select = await findLoadedEventSelect();
    const labels = Array.from(select.options).map((o) => o.textContent);
    expect(labels).toContain('Protest at City Hall');
    expect(labels).toContain('Arrest on Main St');
  });

  it('prefills the clip range from the player marks', async () => {
    renderDialog({ clipStart: 12.5, clipEnd: 47 });

    expect(
      await screen.findByLabelText<HTMLInputElement>('Clip start (s)'),
    ).toHaveValue(12.5);
    expect(
      screen.getByLabelText<HTMLInputElement>('Clip end (s)'),
    ).toHaveValue(47);
  });

  it('posts the evidence link for the chosen event', async () => {
    const user = userEvent.setup();
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.post).mockResolvedValueOnce({});

    const { onClose } = renderDialog({ clipStart: 3, clipEnd: 9 });

    await user.selectOptions(await findLoadedEventSelect(), 'evt-2');
    await user.selectOptions(
      screen.getByLabelText('Relationship'),
      'context',
    );
    await user.click(screen.getByRole('button', { name: 'Link evidence' }));

    await waitFor(() =>
      expect(vi.mocked(apiClient.post)).toHaveBeenCalledWith(
        '/cases/case-1/events/evt-2/evidence',
        {
          asset_id: 'asset-1',
          relationship: 'context',
          clip_start: 3,
          clip_end: 9,
        },
      ),
    );
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it('closes without posting on cancel', async () => {
    const user = userEvent.setup();
    const { apiClient } = await import('@/lib/api-client');

    const { onClose } = renderDialog();

    await user.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(onClose).toHaveBeenCalled();
    expect(vi.mocked(apiClient.post)).not.toHaveBeenCalled();
  });
});
