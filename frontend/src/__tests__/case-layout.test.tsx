/// <reference types="@testing-library/jest-dom" />
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/hooks/use-case', () => ({
  useCase: () => ({ data: { name: 'Smith v. City', status: 'active' } }),
}));

import { CaseLayout } from '@/components/layout/case-layout';

const SECTIONS = [
  'Overview',
  'Assets',
  'Timeline',
  'Conflicts',
  'Clusters',
  'Map',
  'Export',
];

function renderAt(path: string): void {
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/cases/:caseId" element={<CaseLayout />}>
          <Route index element={<div>Overview body</div>} />
          <Route path="assets" element={<div>Assets body</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe('CaseLayout sub-navigation', () => {
  it('links to every case section and renders the active child page', () => {
    renderAt('/cases/c1/assets');
    for (const label of SECTIONS) {
      expect(screen.getByRole('link', { name: label })).toBeInTheDocument();
    }
    expect(screen.getByText('Assets body')).toBeInTheDocument();
  });

  it('marks the active section and offers a back link to the case list', () => {
    renderAt('/cases/c1/assets');
    expect(screen.getByRole('link', { name: 'Assets' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    expect(screen.getByRole('link', { name: /cases/i })).toHaveAttribute(
      'href',
      '/cases',
    );
  });
});
