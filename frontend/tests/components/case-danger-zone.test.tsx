/// <reference types="@testing-library/jest-dom" />
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe } from 'jest-axe';
import { createElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api-client', () => ({
  apiClient: { delete: vi.fn(), patch: vi.fn() },
}));
vi.mock('@/stores/toast-store', () => ({
  useToastStore: { getState: () => ({ addToast: vi.fn() }) },
}));

import { apiClient } from '@/lib/api-client';
import { CaseDangerZone } from '@/components/case/case-danger-zone';
import type { Case } from '@/types';

const mockedDelete = vi.mocked(apiClient.delete);
const mockedPatch = vi.mocked(apiClient.patch);

function makeCase(overrides: Partial<Case> = {}): Case {
  return {
    id: 'c1',
    name: 'Operation Nightingale',
    description: null,
    status: 'closed',
    assetCount: 2,
    eventCount: 0,
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

function wrapper(): React.FC<{ children: React.ReactNode }> {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }) =>
    createElement(QueryClientProvider, { client: qc }, children);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('CaseDangerZone', () => {
  it('disables destroy with a note while the case is active', () => {
    render(
      <CaseDangerZone caseData={makeCase({ status: 'active' })} onPurged={vi.fn()} />,
      { wrapper: wrapper() },
    );

    expect(screen.getByRole('button', { name: 'Destroy…' })).toBeDisabled();
    expect(
      screen.getByText(/close or archive the case before it can be destroyed/i),
    ).toBeInTheDocument();
  });

  it('archives the case through the status endpoint', async () => {
    mockedPatch.mockResolvedValue(makeCase({ status: 'archived' }) as never);
    const user = userEvent.setup();
    render(<CaseDangerZone caseData={makeCase()} onPurged={vi.fn()} />, {
      wrapper: wrapper(),
    });

    await user.click(screen.getByRole('button', { name: 'Archive' }));

    await waitFor(() =>
      expect(mockedPatch).toHaveBeenCalledWith('/cases/c1', {
        status: 'archived',
      }),
    );
  });

  it('keeps destroy disabled until the exact title and a reason are given', async () => {
    const user = userEvent.setup();
    render(<CaseDangerZone caseData={makeCase()} onPurged={vi.fn()} />, {
      wrapper: wrapper(),
    });

    await user.click(screen.getByRole('button', { name: 'Destroy…' }));
    const confirmBtn = screen.getByRole('button', { name: 'Destroy case' });
    expect(confirmBtn).toBeDisabled();

    // wrong title stays disabled
    await user.type(screen.getByLabelText(/type the case title/i), 'wrong');
    await user.type(screen.getByLabelText('Reason'), 'retention elapsed');
    expect(confirmBtn).toBeDisabled();

    // exact title but no reason stays disabled
    await user.clear(screen.getByLabelText(/type the case title/i));
    await user.clear(screen.getByLabelText('Reason'));
    await user.type(
      screen.getByLabelText(/type the case title/i),
      'Operation Nightingale',
    );
    expect(confirmBtn).toBeDisabled();
  });

  it('destroys the case when confirmed and navigates away', async () => {
    mockedDelete.mockResolvedValue(undefined as never);
    const onPurged = vi.fn();
    const user = userEvent.setup();
    render(<CaseDangerZone caseData={makeCase()} onPurged={onPurged} />, {
      wrapper: wrapper(),
    });

    await user.click(screen.getByRole('button', { name: 'Destroy…' }));
    await user.type(
      screen.getByLabelText(/type the case title/i),
      'Operation Nightingale',
    );
    await user.type(screen.getByLabelText('Reason'), 'retention elapsed');
    await user.click(screen.getByRole('button', { name: 'Destroy case' }));

    await waitFor(() =>
      expect(mockedDelete).toHaveBeenCalledWith('/cases/c1', {
        confirm_title: 'Operation Nightingale',
        reason: 'retention elapsed',
      }),
    );
    await waitFor(() => expect(onPurged).toHaveBeenCalled());
  });

  it('has no accessibility violations with the dialog open', async () => {
    const user = userEvent.setup();
    const { container } = render(
      <CaseDangerZone caseData={makeCase()} onPurged={vi.fn()} />,
      { wrapper: wrapper() },
    );

    await user.click(screen.getByRole('button', { name: 'Destroy…' }));
    expect(await axe(container)).toHaveNoViolations();
  });
});
