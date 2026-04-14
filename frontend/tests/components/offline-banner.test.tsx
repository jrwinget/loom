import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest';
import {
  OfflineBanner,
} from '@/components/layout/offline-banner';
import {
  useOfflineQueueStore,
} from '@/stores/offline-queue-store';

function renderBanner(): void {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <OfflineBanner />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('OfflineBanner', () => {
  let onLineSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    onLineSpy = vi.spyOn(navigator, 'onLine', 'get');
    onLineSpy.mockReturnValue(true);
    useOfflineQueueStore.setState({ queue: [] });
  });

  afterEach(() => {
    onLineSpy.mockRestore();
    localStorage.clear();
  });

  it('renders nothing when online with empty queue', () => {
    onLineSpy.mockReturnValue(true);
    renderBanner();

    expect(
      screen.queryByTestId('offline-banner'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('sync-banner'),
    ).not.toBeInTheDocument();
  });

  it('shows offline banner when offline', () => {
    onLineSpy.mockReturnValue(false);
    renderBanner();

    expect(
      screen.getByTestId('offline-banner'),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/you are offline/i),
    ).toBeInTheDocument();
  });

  it('shows queue count when offline with items', () => {
    onLineSpy.mockReturnValue(false);
    useOfflineQueueStore.getState().enqueue({
      type: 'annotation',
      payload: { method: 'POST', path: '/test' },
    });
    useOfflineQueueStore.getState().enqueue({
      type: 'event',
      payload: { method: 'POST', path: '/test2' },
    });

    renderBanner();

    expect(
      screen.getByText(/2 items pending sync/i),
    ).toBeInTheDocument();
  });

  it('can be dismissed', async () => {
    onLineSpy.mockReturnValue(false);
    const user = userEvent.setup();
    renderBanner();

    const dismissBtn = screen.getByLabelText(
      /dismiss offline notification/i,
    );
    await user.click(dismissBtn);

    expect(
      screen.queryByTestId('offline-banner'),
    ).not.toBeInTheDocument();
  });

  it('shows singular text for 1 item', () => {
    onLineSpy.mockReturnValue(false);
    useOfflineQueueStore.getState().enqueue({
      type: 'annotation',
      payload: { method: 'POST', path: '/test' },
    });

    renderBanner();

    expect(
      screen.getByText(/1 item pending sync/i),
    ).toBeInTheDocument();
  });
});
