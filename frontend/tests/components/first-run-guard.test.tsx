/// <reference types="@testing-library/jest-dom" />
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { MemoryRouter, useLocation } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api-client', () => ({
  apiClient: { get: vi.fn() },
}));

import { apiClient } from '@/lib/api-client';
import { FirstRunGuard } from '@/components/auth/first-run-guard';

const mockedGet = vi.mocked(apiClient.get);

function LocationProbe(): React.ReactElement {
  return <div data-testid="pathname">{useLocation().pathname}</div>;
}

function renderGuard(initialPath: string): void {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    createElement(
      QueryClientProvider,
      { client: qc },
      createElement(
        MemoryRouter,
        { initialEntries: [initialPath] },
        createElement(FirstRunGuard, null, createElement(LocationProbe)),
      ),
    ),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('FirstRunGuard', () => {
  it('redirects to first-run when the deploy has no users yet', async () => {
    mockedGet.mockResolvedValue({
      firstRunRequired: true,
      deploymentProfile: 'server',
    });

    renderGuard('/dashboard');

    await waitFor(() =>
      expect(screen.getByTestId('pathname')).toHaveTextContent('/first-run'),
    );
  });

  it('renders children in place when first run is not required', async () => {
    mockedGet.mockResolvedValue({
      firstRunRequired: false,
      deploymentProfile: 'server',
    });

    renderGuard('/dashboard');

    await waitFor(() => expect(mockedGet).toHaveBeenCalled());
    expect(screen.getByTestId('pathname')).toHaveTextContent('/dashboard');
  });
});
