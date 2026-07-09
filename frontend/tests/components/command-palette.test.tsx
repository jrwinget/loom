/// <reference types="@testing-library/jest-dom" />
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { CommandPalette } from '@/components/layout/command-palette';
import type { GlobalSearchResult } from '@/hooks/use-global-search';

const mockNavigate = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => mockNavigate };
});

let results: GlobalSearchResult[] = [];
vi.mock('@/hooks/use-global-search', () => ({
  useGlobalSearch: () => ({ data: { results } }),
}));

function open(): void {
  render(
    <MemoryRouter>
      <CommandPalette />
    </MemoryRouter>,
  );
  fireEvent.keyDown(document, { key: 'k', metaKey: true });
}

describe('CommandPalette', () => {
  beforeEach(() => {
    results = [];
    mockNavigate.mockReset();
  });

  it('is hidden until the cmd+k shortcut fires', () => {
    render(
      <MemoryRouter>
        <CommandPalette />
      </MemoryRouter>,
    );
    expect(screen.queryByTestId('command-palette')).not.toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'k', metaKey: true });
    expect(screen.getByTestId('command-palette')).toBeInTheDocument();
  });

  it('routes to a result on select', async () => {
    results = [
      {
        type: 'asset',
        id: 'a1',
        caseId: 'c1',
        title: 'clip.mp4',
        snippet: null,
      },
    ];
    open();
    const item = await screen.findByText('clip.mp4');
    fireEvent.click(item);
    // assets route to the case's assets tab
    expect(mockNavigate).toHaveBeenCalledWith('/cases/c1/assets');
  });

  it('offers static navigation actions', async () => {
    open();
    fireEvent.click(await screen.findByText('Go to Cases'));
    expect(mockNavigate).toHaveBeenCalledWith('/cases');
  });

  it('always offers the actions group even with no query', () => {
    open();
    // below the search threshold there are no results, but the
    // static actions remain reachable
    expect(screen.getByText('Go to Dashboard')).toBeInTheDocument();
    expect(screen.queryByTestId('palette-no-matches')).not.toBeInTheDocument();
  });
});
