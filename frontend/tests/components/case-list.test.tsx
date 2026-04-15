import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { CaseList } from '@/components/case/case-list';
import type { Case } from '@/types';

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom');
  return { ...actual, useNavigate: () => vi.fn() };
});

const mockCases: Case[] = [
  {
    id: '1',
    name: 'Case Alpha',
    description: 'First case',
    status: 'active',
    assetCount: 3,
    eventCount: 7,
    createdAt: '2026-01-01T00:00:00Z',
  },
  {
    id: '2',
    name: 'Case Beta',
    description: 'Second case',
    status: 'archived',
    assetCount: 1,
    eventCount: 2,
    createdAt: '2026-02-01T00:00:00Z',
  },
];

function renderList(
  props: { cases: Case[]; isLoading: boolean },
): void {
  render(
    <MemoryRouter>
      <CaseList {...props} />
    </MemoryRouter>,
  );
}

describe('CaseList', () => {
  it('renders correct number of cards', () => {
    renderList({ cases: mockCases, isLoading: false });
    expect(
      screen.getByText('Case Alpha'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Case Beta'),
    ).toBeInTheDocument();
  });

  it('shows skeleton when loading', () => {
    renderList({ cases: [], isLoading: true });
    const skeletons = screen.getAllByTestId(
      'case-skeleton',
    );
    expect(skeletons).toHaveLength(6);
  });

  it('shows empty state when no cases', () => {
    renderList({ cases: [], isLoading: false });
    expect(
      screen.getByTestId('empty-state'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('No cases yet'),
    ).toBeInTheDocument();
  });
});
