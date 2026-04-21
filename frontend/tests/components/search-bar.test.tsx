import {
  render,
  screen,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from
  '@tanstack/react-query';
import { describe, expect, it, vi } from 'vitest';
import { SearchBar } from
  '@/components/review/search-bar';

// mock the search hook
vi.mock('@/hooks/use-search', () => ({
  useSearch: () => ({
    data: {
      results: [
        {
          type: 'transcript',
          id: 'r1',
          text: 'test result one',
          assetId: 'a1',
          relevanceScore: 0.9,
          metadata: {},
        },
        {
          type: 'annotation',
          id: 'r2',
          text: 'another test hit',
          assetId: 'a2',
          relevanceScore: 0.8,
          metadata: {},
        },
      ],
      total: 2,
      facets: {},
    },
    isLoading: false,
  }),
}));

// mock keyboard shortcut
vi.mock('@/hooks/use-keyboard', () => ({
  useKeyboardShortcut: vi.fn(),
}));

function renderWithQuery(
  ui: React.ReactElement,
): ReturnType<typeof render> {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      {ui}
    </QueryClientProvider>,
  );
}

describe('SearchBar', () => {
  it('renders search input', () => {
    renderWithQuery(
      <SearchBar caseId="case-1" />,
    );
    expect(
      screen.getByTestId('search-input'),
    ).toBeInTheDocument();
  });

  it('shows results dropdown on type', async () => {
    const user = userEvent.setup();
    renderWithQuery(
      <SearchBar caseId="case-1" />,
    );

    const input = screen.getByTestId('search-input');
    await user.type(input, 'test query');

    expect(
      screen.getByTestId('search-results'),
    ).toBeInTheDocument();
  });

  it('displays result text', async () => {
    const user = userEvent.setup();
    renderWithQuery(
      <SearchBar caseId="case-1" />,
    );

    const input = screen.getByTestId('search-input');
    await user.type(input, 'test');

    // should find the result text
    expect(
      screen.getByTestId('search-result-r1'),
    ).toBeInTheDocument();
  });

  it('calls onResultClick when result clicked',
    async () => {
      const user = userEvent.setup();
      const onClick = vi.fn();
      renderWithQuery(
        <SearchBar
          caseId="case-1"
          onResultClick={onClick}
        />,
      );

      const input = screen.getByTestId('search-input');
      await user.type(input, 'test');

      const result = screen.getByTestId(
        'search-result-r1',
      );
      await user.click(result);
      expect(onClick).toHaveBeenCalledTimes(1);
    },
  );
});
