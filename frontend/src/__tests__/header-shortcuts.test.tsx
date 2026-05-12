/// <reference types="@testing-library/jest-dom" />
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { Header } from '@/components/layout/header';
import type { AuthState } from '@/stores/auth-store';

vi.mock('@/stores/auth-store', () => ({
  useAuthStore: Object.assign(
    vi.fn((selector: (s: AuthState) => unknown) =>
      selector({
        token: 't',
        user: { id: '1', email: 'u@example.com', role: 'admin' },
        mfaChallengeToken: null,
        setAuth: vi.fn(),
        clearAuth: vi.fn(),
        setMfaChallenge: vi.fn(),
        clearMfaChallenge: vi.fn(),
      } as unknown as AuthState),
    ),
    { getState: () => ({ clearAuth: vi.fn() }) },
  ),
}));

function renderHeader(): void {
  render(
    <MemoryRouter>
      <Header />
    </MemoryRouter>,
  );
}

describe('Header keyboard shortcuts dialog', () => {
  it('renders nothing for the dialog until the trigger is clicked', () => {
    renderHeader();
    expect(screen.queryByTestId('shortcuts-dialog')).not.toBeInTheDocument();
  });

  it('opens the shortcuts dialog when the ? button is activated', async () => {
    const user = userEvent.setup();
    renderHeader();
    await user.click(screen.getByTestId('open-shortcuts'));
    expect(screen.getByTestId('shortcuts-dialog')).toBeInTheDocument();
    expect(screen.getByText('Play / pause')).toBeInTheDocument();
  });
});
