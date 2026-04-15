/// <reference types="@testing-library/jest-dom" />
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { ProtectedRoute } from '@/components/auth/protected-route';
import type { AuthState } from '@/stores/auth-store';

vi.mock('@/stores/auth-store', () => ({
  useAuthStore: vi.fn(),
}));

import { useAuthStore } from '@/stores/auth-store';

const mockedUseAuthStore = vi.mocked(useAuthStore);

function renderWithRouter(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <Routes>
        <Route path="/login" element={<div>Login page</div>} />
        <Route element={<ProtectedRoute />}>
          <Route path="/dashboard" element={<div>Dashboard</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe('ProtectedRoute', () => {
  it('redirects to /login when no token', () => {
    mockedUseAuthStore.mockImplementation(
      (selector: (s: AuthState) => unknown) =>
        selector({
          token: null,
          user: null,
          mfaChallengeToken: null,
          setAuth: vi.fn(),
          clearAuth: vi.fn(),
          setMfaChallenge: vi.fn(),
          clearMfaChallenge: vi.fn(),
          isAuthenticated: () => false,
          requiresMfa: () => false,
        }),
    );

    renderWithRouter('/dashboard');

    expect(screen.getByText('Login page')).toBeInTheDocument();
    expect(screen.queryByText('Dashboard')).not.toBeInTheDocument();
  });

  it('renders children when token exists', () => {
    mockedUseAuthStore.mockImplementation(
      (selector: (s: AuthState) => unknown) =>
        selector({
          token: 'valid-token',
          user: null,
          mfaChallengeToken: null,
          setAuth: vi.fn(),
          clearAuth: vi.fn(),
          setMfaChallenge: vi.fn(),
          clearMfaChallenge: vi.fn(),
          isAuthenticated: () => true,
          requiresMfa: () => false,
        }),
    );

    renderWithRouter('/dashboard');

    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.queryByText('Login page')).not.toBeInTheDocument();
  });
});
