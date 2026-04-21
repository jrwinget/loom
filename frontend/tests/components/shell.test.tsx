import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { Shell } from '@/components/layout/shell';

function renderWithProviders(): void {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <Shell />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Shell', () => {
  it('renders sidebar', () => {
    renderWithProviders();
    expect(screen.getByTestId('sidebar')).toBeInTheDocument();
  });

  it('renders main content area', () => {
    renderWithProviders();
    expect(
      screen.getByTestId('main-content'),
    ).toBeInTheDocument();
  });
});
