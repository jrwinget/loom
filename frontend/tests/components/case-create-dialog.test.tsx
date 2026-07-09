/// <reference types="@testing-library/jest-dom" />
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe } from 'jest-axe';
import { createElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api-client', () => ({
  apiClient: { post: vi.fn() },
}));
vi.mock('@/stores/toast-store', () => ({
  useToastStore: { getState: () => ({ addToast: vi.fn() }) },
}));

import { apiClient } from '@/lib/api-client';
import { CaseCreateDialog } from '@/components/case/case-create-dialog';

const mockedPost = vi.mocked(apiClient.post);

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

describe('CaseCreateDialog', () => {
  it('does not submit when the name is blank', async () => {
    const user = userEvent.setup();
    render(<CaseCreateDialog open onOpenChange={vi.fn()} />, {
      wrapper: wrapper(),
    });

    await user.click(screen.getByRole('button', { name: 'Create' }));

    expect(mockedPost).not.toHaveBeenCalled();
  });

  it('trims the name and omits an empty description on create', async () => {
    mockedPost.mockResolvedValue({ id: 'c1' } as never);
    const user = userEvent.setup();
    render(<CaseCreateDialog open onOpenChange={vi.fn()} />, {
      wrapper: wrapper(),
    });

    await user.type(
      screen.getByPlaceholderText('Case name'),
      '  Nightingale  ',
    );
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() =>
      expect(mockedPost).toHaveBeenCalledWith('/cases', {
        name: 'Nightingale',
        description: undefined,
      }),
    );
  });

  it('closes the dialog after a successful create', async () => {
    mockedPost.mockResolvedValue({ id: 'c1' } as never);
    const onOpenChange = vi.fn();
    const user = userEvent.setup();
    render(<CaseCreateDialog open onOpenChange={onOpenChange} />, {
      wrapper: wrapper(),
    });

    await user.type(screen.getByPlaceholderText('Case name'), 'Nightingale');
    await user.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
  });

  it('has no accessibility violations when open', async () => {
    const { baseElement } = render(
      <CaseCreateDialog open onOpenChange={vi.fn()} />,
      { wrapper: wrapper() },
    );

    expect(await axe(baseElement)).toHaveNoViolations();
  });
});
