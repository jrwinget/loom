import { render, screen, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { PluginList } from '@/components/plugin/plugin-list';
import type { PluginListResponse } from '@/types/plugin';

vi.mock('@/hooks/use-plugins', () => ({
  usePlugins: vi.fn(),
  useCreatePlugin: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
  })),
  useUpdatePlugin: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
  })),
}));

import { usePlugins } from '@/hooks/use-plugins';

const mockUsePlugins = vi.mocked(usePlugins);

function makeListResponse(
  overrides: Partial<PluginListResponse> = {},
): PluginListResponse {
  return {
    items: [
      {
        id: 'plugin-1',
        name: 'Slack Notifier',
        description: 'Posts to Slack on events',
        version: '1.0.0',
        pluginType: 'webhook',
        isEnabled: true,
        config: null,
        createdBy: 'user-1',
        createdAt: '2025-01-01T00:00:00Z',
        updatedAt: '2025-01-01T00:00:00Z',
      },
      {
        id: 'plugin-2',
        name: 'Custom OCR',
        description: null,
        version: '2.0.0',
        pluginType: 'activity',
        isEnabled: false,
        config: null,
        createdBy: 'user-1',
        createdAt: '2025-01-01T00:00:00Z',
        updatedAt: '2025-01-01T00:00:00Z',
      },
    ],
    total: 2,
    ...overrides,
  };
}

function renderComponent(): void {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <PluginList />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('PluginList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders plugin cards', () => {
    mockUsePlugins.mockReturnValue({
      data: makeListResponse(),
      isLoading: false,
    } as ReturnType<typeof usePlugins>);

    renderComponent();

    expect(screen.getByText('Slack Notifier')).toBeInTheDocument();
    expect(screen.getByText('Custom OCR')).toBeInTheDocument();
  });

  it('renders type badges', () => {
    mockUsePlugins.mockReturnValue({
      data: makeListResponse(),
      isLoading: false,
    } as ReturnType<typeof usePlugins>);

    renderComponent();

    expect(screen.getByTestId('type-badge-webhook')).toBeInTheDocument();
    expect(screen.getByTestId('type-badge-activity')).toBeInTheDocument();
  });

  it('renders enabled/disabled toggle', () => {
    mockUsePlugins.mockReturnValue({
      data: makeListResponse(),
      isLoading: false,
    } as ReturnType<typeof usePlugins>);

    renderComponent();

    expect(screen.getByTestId('toggle-plugin-1')).toHaveTextContent('Enabled');
    expect(screen.getByTestId('toggle-plugin-2')).toHaveTextContent('Disabled');
  });

  it('shows empty state', () => {
    mockUsePlugins.mockReturnValue({
      data: { items: [], total: 0 },
      isLoading: false,
    } as ReturnType<typeof usePlugins>);

    renderComponent();

    expect(screen.getByText('No plugins installed')).toBeInTheDocument();
  });

  it('shows loading state', () => {
    mockUsePlugins.mockReturnValue({
      data: undefined,
      isLoading: true,
    } as ReturnType<typeof usePlugins>);

    renderComponent();

    expect(screen.getByTestId('plugin-list-loading')).toBeInTheDocument();
  });

  it('opens create dialog', () => {
    mockUsePlugins.mockReturnValue({
      data: makeListResponse(),
      isLoading: false,
    } as ReturnType<typeof usePlugins>);

    renderComponent();

    fireEvent.click(screen.getByTestId('create-plugin-btn'));
    expect(screen.getByTestId('create-plugin-dialog')).toBeInTheDocument();
  });
});
