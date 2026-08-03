/// <reference types="@testing-library/jest-dom" />
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe } from 'jest-axe';
import { createElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api-client', () => ({
  apiClient: { delete: vi.fn(), patch: vi.fn(), post: vi.fn() },
}));
vi.mock('@/stores/toast-store', () => ({
  useToastStore: { getState: () => ({ addToast: vi.fn() }) },
}));

import { apiClient } from '@/lib/api-client';
import { CaseDangerZone } from '@/components/case/case-danger-zone';
import type { Case } from '@/types';

const mockedDelete = vi.mocked(apiClient.delete);
const mockedPatch = vi.mocked(apiClient.patch);
const mockedPost = vi.mocked(apiClient.post);

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
    holdActive: false,
    holdReason: null,
    holdSetBy: null,
    holdSetAt: null,
    ...overrides,
  };
}

function makeHeldCase(overrides: Partial<Case> = {}): Case {
  return makeCase({
    holdActive: true,
    holdReason: 'Doe v. City litigation',
    holdSetBy: 'u1',
    holdSetAt: '2026-07-20T12:00:00Z',
    ...overrides,
  });
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

  it('keeps set hold disabled until a reason is given, then posts it', async () => {
    mockedPost.mockResolvedValue(makeHeldCase() as never);
    const user = userEvent.setup();
    render(<CaseDangerZone caseData={makeCase()} onPurged={vi.fn()} />, {
      wrapper: wrapper(),
    });

    const setBtn = screen.getByRole('button', { name: 'Set hold' });
    expect(setBtn).toBeDisabled();

    // whitespace alone does not arm the button
    await user.type(screen.getByLabelText(/reason for the hold/i), '   ');
    expect(setBtn).toBeDisabled();

    await user.clear(screen.getByLabelText(/reason for the hold/i));
    await user.type(
      screen.getByLabelText(/reason for the hold/i),
      'pending litigation',
    );
    expect(setBtn).toBeEnabled();

    await user.click(setBtn);
    await waitFor(() =>
      expect(mockedPost).toHaveBeenCalledWith('/cases/c1/hold', {
        reason: 'pending litigation',
      }),
    );
  });

  it('shows the hold reason and date, and disables archive and destroy while held', () => {
    render(<CaseDangerZone caseData={makeHeldCase()} onPurged={vi.fn()} />, {
      wrapper: wrapper(),
    });

    expect(screen.getByText(/doe v\. city litigation/i)).toBeInTheDocument();
    expect(screen.getByText(/jul 20, 2026/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Archive' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Destroy…' })).toBeDisabled();
    expect(
      screen.getAllByText(/disabled while the case is under litigation hold/i)
        .length,
    ).toBeGreaterThan(0);
  });

  it('keeps the purge dialog unreachable while held even when closed', async () => {
    const user = userEvent.setup();
    render(
      <CaseDangerZone
        caseData={makeHeldCase({ status: 'closed' })}
        onPurged={vi.fn()}
      />,
      { wrapper: wrapper() },
    );

    const destroyBtn = screen.getByRole('button', { name: 'Destroy…' });
    expect(destroyBtn).toBeDisabled();
    await user.click(destroyBtn);
    expect(screen.queryByTestId('case-purge-dialog')).not.toBeInTheDocument();
  });

  it('requires a reason to release the hold, then posts it', async () => {
    mockedPost.mockResolvedValue(makeCase() as never);
    const user = userEvent.setup();
    render(<CaseDangerZone caseData={makeHeldCase()} onPurged={vi.fn()} />, {
      wrapper: wrapper(),
    });

    const releaseBtn = screen.getByRole('button', { name: 'Release hold' });
    expect(releaseBtn).toBeDisabled();

    await user.type(
      screen.getByLabelText(/reason for releasing/i),
      'matter settled',
    );
    expect(releaseBtn).toBeEnabled();

    await user.click(releaseBtn);
    await waitFor(() =>
      expect(mockedPost).toHaveBeenCalledWith('/cases/c1/hold/release', {
        reason: 'matter settled',
      }),
    );
  });

  it('has no accessibility violations with the hold card shown', async () => {
    const { container } = render(
      <CaseDangerZone caseData={makeHeldCase()} onPurged={vi.fn()} />,
      { wrapper: wrapper() },
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});
