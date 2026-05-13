/// <reference types="@testing-library/jest-dom" />
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// the LoginPage imports `isTauri` as a top-level const from
// tauri-bridge. mock the whole module so each test can set the value
// it needs (lite-tauri vs lite-web vs server).
let mockedIsTauri = false;

vi.mock('@/lib/tauri-bridge', () => ({
  get isTauri() {
    return mockedIsTauri;
  },
  factoryReset: vi.fn(),
}));

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { apiClient } from '@/lib/api-client';
import { LoginPage } from '@/routes/login';

const mockedGet = vi.mocked(apiClient.get);

function renderLogin() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/login']}>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/first-run" element={<div>First run page</div>} />
          <Route path="/forgot-password" element={<div>Forgot</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('LoginPage recovery affordances', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    mockedIsTauri = false;
  });

  it('shows the forgot-password link and Reset Loom button on lite + tauri', async () => {
    mockedIsTauri = true;
    mockedGet.mockResolvedValueOnce({
      first_run_required: false,
      deployment_profile: 'lite',
      data_dir: '/home/user/.loom/data',
    });

    renderLogin();

    expect(
      await screen.findByTestId('forgot-password-link'),
    ).toBeInTheDocument();
    expect(screen.getByTestId('factory-reset-link')).toBeInTheDocument();
  });

  it('shows the forgot-password link on lite + web (no factory reset)', async () => {
    mockedIsTauri = false;
    mockedGet.mockResolvedValueOnce({
      first_run_required: false,
      deployment_profile: 'lite',
      data_dir: null,
    });

    renderLogin();

    expect(
      await screen.findByTestId('forgot-password-link'),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('factory-reset-link')).not.toBeInTheDocument();
  });

  it('hides both affordances on the server profile, even inside tauri', async () => {
    mockedIsTauri = true;
    mockedGet.mockResolvedValueOnce({
      first_run_required: false,
      deployment_profile: 'server',
      data_dir: null,
    });

    renderLogin();

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /sign in/i })).toBeVisible();
    });
    expect(
      screen.queryByTestId('forgot-password-link'),
    ).not.toBeInTheDocument();
    expect(screen.queryByTestId('factory-reset-link')).not.toBeInTheDocument();
  });
});
