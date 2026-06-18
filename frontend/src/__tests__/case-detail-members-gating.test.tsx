/// <reference types="@testing-library/jest-dom" />
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/hooks/use-case', () => ({
  useCase: () => ({
    data: { name: 'C', status: 'active', assetCount: 0, eventCount: 0 },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useCaseMembers: () => ({ data: [] }),
}));
vi.mock('@/hooks/use-audit', () => ({
  useCaseAudit: () => ({ data: { items: [] } }),
}));
vi.mock('@/hooks/use-first-run', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/hooks/use-first-run')>();
  return { ...actual, useFirstRunStatus: vi.fn() };
});

import { useFirstRunStatus } from '@/hooks/use-first-run';
import { CaseDetailPage } from '@/routes/cases/[caseId]/index';

const mockedStatus = vi.mocked(useFirstRunStatus);

function setProfile(deploymentProfile: 'lite' | 'server'): void {
  mockedStatus.mockReturnValue({
    data: { firstRunRequired: false, deploymentProfile, dataDir: null },
  } as unknown as ReturnType<typeof useFirstRunStatus>);
}

function renderPage(): void {
  render(
    <MemoryRouter initialEntries={['/cases/c1']}>
      <Routes>
        <Route path="/cases/:caseId" element={<CaseDetailPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe('Case detail Members tab gating', () => {
  beforeEach(() => vi.clearAllMocks());

  it('hides the Members tab on lite (single-user)', () => {
    setProfile('lite');
    renderPage();
    expect(
      screen.queryByRole('tab', { name: 'Members' }),
    ).not.toBeInTheDocument();
  });

  it('shows the Members tab on server', () => {
    setProfile('server');
    renderPage();
    expect(screen.getByRole('tab', { name: 'Members' })).toBeInTheDocument();
  });
});
