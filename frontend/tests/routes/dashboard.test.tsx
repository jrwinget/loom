/// <reference types="@testing-library/jest-dom" />
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { axe } from 'jest-axe';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Dashboard } from '@/routes/index';
import { useJobStore } from '@/stores/job-store';
import type { Case } from '@/types';

const { casesState, storageState, auditState } = vi.hoisted(() => ({
  casesState: {
    current: {
      data: undefined as Case[] | undefined,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    },
  },
  storageState: { current: { data: undefined as unknown } },
  auditState: { current: { data: undefined as unknown } },
}));

vi.mock('@/hooks/use-case', () => ({
  useCases: () => casesState.current,
  useCreateCase: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock('@/hooks/use-storage', () => ({
  useStorageUsage: () => storageState.current,
}));

vi.mock('@/hooks/use-audit', () => ({
  useCaseAudit: () => auditState.current,
}));

function makeCase(over: Partial<Case> = {}): Case {
  return {
    id: 'case-1',
    name: 'March 12 Action',
    description: null,
    status: 'active',
    assetCount: 3,
    eventCount: 5,
    createdAt: '2026-06-01T00:00:00Z',
    updatedAt: '2026-07-01T00:00:00Z',
    ...over,
  };
}

function renderDashboard(): ReturnType<typeof render> {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <Dashboard />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Dashboard', () => {
  beforeEach(() => {
    useJobStore.setState({ jobs: [] });
    casesState.current = {
      data: undefined,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    };
    storageState.current = { data: undefined };
    auditState.current = { data: undefined };
  });

  it('keeps the create-first-case call to action when empty', () => {
    casesState.current.data = [];
    renderDashboard();
    expect(screen.getByTestId('dashboard-empty')).toHaveTextContent(
      'Create your first case',
    );
  });

  it('shows recent cases sorted by last update', () => {
    casesState.current.data = [
      makeCase({ id: 'old', name: 'Old', updatedAt: '2026-01-01T00:00:00Z' }),
      makeCase({ id: 'new', name: 'New', updatedAt: '2026-07-08T00:00:00Z' }),
    ];
    renderDashboard();

    const cards = screen.getAllByText(/Old|New/);
    expect(cards[0]).toHaveTextContent('New');
  });

  it('shows running jobs from the registry', () => {
    casesState.current.data = [makeCase()];
    useJobStore.getState().registerJob({
      workflowId: 'transcribe-1',
      caseId: 'case-1',
      kind: 'transcription',
      label: 'clip.mp4',
    });
    renderDashboard();

    expect(screen.getByTestId('dashboard-jobs')).toHaveTextContent('clip.mp4');
  });

  it('shows the storage advisory only when the endpoint answers', () => {
    casesState.current.data = [makeCase()];
    renderDashboard();
    expect(screen.queryByTestId('dashboard-storage')).not.toBeInTheDocument();

    storageState.current = {
      data: { freeBytes: 5 * 1024 ** 3, totalBytes: 10 * 1024 ** 3 },
    };
    renderDashboard();
    expect(screen.getByTestId('dashboard-storage')).toHaveTextContent(
      '5.0 GB free of 10.0 GB',
    );
  });

  it('shows recent activity for the most recent case', () => {
    casesState.current.data = [makeCase()];
    auditState.current = {
      data: {
        items: [
          {
            id: 'a1',
            actorId: 'u1',
            action: 'asset_uploaded',
            resourceType: 'asset',
            resourceId: 'x',
            detail: null,
            ipAddress: null,
            userAgent: null,
            timestamp: '2026-07-08T12:00:00Z',
          },
        ],
        total: 1,
      },
    };
    renderDashboard();

    expect(screen.getByTestId('dashboard-activity')).toHaveTextContent(
      'asset uploaded',
    );
  });

  it('has no axe violations', async () => {
    casesState.current.data = [makeCase()];
    const { container } = renderDashboard();
    expect(await axe(container)).toHaveNoViolations();
  });
});
