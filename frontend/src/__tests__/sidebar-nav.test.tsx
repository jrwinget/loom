/// <reference types="@testing-library/jest-dom" />
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/hooks/use-first-run', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/hooks/use-first-run')>();
  return { ...actual, useFirstRunStatus: vi.fn() };
});

import { useFirstRunStatus } from '@/hooks/use-first-run';
import { useUiStore } from '@/stores/ui-store';
import { Sidebar } from '@/components/layout/sidebar';

const mockedStatus = vi.mocked(useFirstRunStatus);

function setProfile(deploymentProfile: 'lite' | 'server'): void {
  mockedStatus.mockReturnValue({
    data: { firstRunRequired: false, deploymentProfile, dataDir: null },
  } as unknown as ReturnType<typeof useFirstRunStatus>);
}

function renderSidebar(): void {
  render(
    <MemoryRouter>
      <Sidebar />
    </MemoryRouter>,
  );
}

describe('Sidebar deployment-profile gating', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useUiStore.setState({ sidebarOpen: true });
  });

  it('on lite hides Organizations, points Settings at Security, shows Storage', () => {
    setProfile('lite');
    renderSidebar();
    expect(
      screen.queryByRole('link', { name: 'Organizations' }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Settings' })).toHaveAttribute(
      'href',
      '/settings/security',
    );
    expect(screen.getByRole('link', { name: 'Storage' })).toBeInTheDocument();
  });

  it('on server shows Organizations, points Settings at Plugins, no Storage', () => {
    setProfile('server');
    renderSidebar();
    expect(
      screen.getByRole('link', { name: 'Organizations' }),
    ).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Settings' })).toHaveAttribute(
      'href',
      '/settings/plugins',
    );
    expect(
      screen.queryByRole('link', { name: 'Storage' }),
    ).not.toBeInTheDocument();
  });
});
