/// <reference types="@testing-library/jest-dom" />
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { axe } from 'jest-axe';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Breadcrumbs } from '@/components/layout/breadcrumbs';

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

import { apiClient } from '@/lib/api-client';

const mockedGet = vi.mocked(apiClient.get);

function renderAt(pathname: string): ReturnType<typeof render> {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[pathname]}>
        <Breadcrumbs />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Breadcrumbs', () => {
  beforeEach(() => {
    mockedGet.mockReset();
  });

  it('shows only Home on the dashboard', () => {
    renderAt('/');
    const nav = screen.getByRole('navigation', { name: 'Breadcrumb' });
    expect(nav).toHaveTextContent('Home');
    expect(screen.queryByText('Cases')).not.toBeInTheDocument();
  });

  it('marks the leaf with aria-current on the cases list', () => {
    renderAt('/cases');
    expect(screen.getByText('Cases')).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: 'Home' })).toHaveAttribute(
      'href',
      '/',
    );
  });

  it('resolves the case name from the case query', async () => {
    mockedGet.mockResolvedValueOnce({
      id: 'case-1',
      name: 'March 12 Action',
    });
    renderAt('/cases/case-1/timeline');

    expect(await screen.findByText('March 12 Action')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: 'March 12 Action' }),
    ).toHaveAttribute('href', '/cases/case-1');
    expect(screen.getByText('Timeline')).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('falls back to a neutral case label while loading', () => {
    mockedGet.mockReturnValueOnce(new Promise(() => {}));
    renderAt('/cases/case-1/assets');

    expect(screen.getByText('Case')).toBeInTheDocument();
    expect(screen.getByText('Assets')).toHaveAttribute('aria-current', 'page');
  });

  it('renders the settings group as plain text with the page as leaf', () => {
    renderAt('/settings/ai');

    expect(screen.getByText('Settings')).not.toHaveAttribute('href');
    expect(screen.getByText('AI')).toHaveAttribute('aria-current', 'page');
  });

  it('labels the review workspace', async () => {
    mockedGet.mockResolvedValueOnce({ id: 'case-1', name: 'Case A' });
    renderAt('/cases/case-1/review/asset-9');

    expect(await screen.findByText('Review')).toHaveAttribute(
      'aria-current',
      'page',
    );
  });

  it('has no axe violations', async () => {
    const { container } = renderAt('/cases');
    expect(await axe(container)).toHaveNoViolations();
  });
});
