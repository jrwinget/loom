import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { WebhookConfig } from '@/components/plugin/webhook-config';
import type { WebhookListResponse } from '@/types/plugin';

vi.mock('@/hooks/use-plugins', () => ({
  useWebhooks: vi.fn(),
  useCreateWebhook: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
  })),
  useWebhookDeliveries: vi.fn(() => ({
    data: { items: [], total: 0 },
    isLoading: false,
  })),
}));

import { useWebhooks } from '@/hooks/use-plugins';

const mockUseWebhooks = vi.mocked(useWebhooks);

function makeWebhookList(
  overrides: Partial<WebhookListResponse> = {},
): WebhookListResponse {
  return {
    items: [
      {
        id: 'wh-1',
        pluginId: 'plugin-1',
        url: 'https://example.com/hook',
        events: ['asset.uploaded', 'asset.processed'],
        isActive: true,
        lastTriggeredAt: null,
        failureCount: 0,
        createdAt: '2025-01-01T00:00:00Z',
        updatedAt: '2025-01-01T00:00:00Z',
      },
    ],
    total: 1,
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
        <WebhookConfig pluginId="plugin-1" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('WebhookConfig', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders webhook form', () => {
    mockUseWebhooks.mockReturnValue({
      data: { items: [], total: 0 },
      isLoading: false,
    } as ReturnType<typeof useWebhooks>);

    renderComponent();

    expect(screen.getByTestId('webhook-config')).toBeInTheDocument();
    expect(screen.getByLabelText('URL')).toBeInTheDocument();
    expect(screen.getByLabelText('Secret (optional)')).toBeInTheDocument();
  });

  it('renders event checkboxes', () => {
    mockUseWebhooks.mockReturnValue({
      data: { items: [], total: 0 },
      isLoading: false,
    } as ReturnType<typeof useWebhooks>);

    renderComponent();

    const checkboxes = screen.getByTestId('event-checkboxes');
    expect(checkboxes).toBeInTheDocument();
    expect(screen.getByText('asset.uploaded')).toBeInTheDocument();
    expect(screen.getByText('case.created')).toBeInTheDocument();
    expect(screen.getByText('export.completed')).toBeInTheDocument();
  });

  it('renders existing webhooks', () => {
    mockUseWebhooks.mockReturnValue({
      data: makeWebhookList(),
      isLoading: false,
    } as ReturnType<typeof useWebhooks>);

    renderComponent();

    expect(screen.getByText('https://example.com/hook')).toBeInTheDocument();
    expect(screen.getByText('Active')).toBeInTheDocument();
  });

  it('shows empty state for webhooks', () => {
    mockUseWebhooks.mockReturnValue({
      data: { items: [], total: 0 },
      isLoading: false,
    } as ReturnType<typeof useWebhooks>);

    renderComponent();

    expect(screen.getByText('No webhooks configured')).toBeInTheDocument();
  });
});
