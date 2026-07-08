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
      firstRunRequired: false,
      deploymentProfile: 'lite',
      dataDir: '/home/user/.loom/data',
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
      firstRunRequired: false,
      deploymentProfile: 'lite',
      dataDir: null,
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
      firstRunRequired: false,
      deploymentProfile: 'server',
      dataDir: null,
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

  it('renders a loading placeholder while the status query is in flight', async () => {
    // never resolve the query, keep it in the loading state for the
    // duration of the assertion. the affordance block must not be
    // hidden — that was the v0.1.2 regression that stranded users.
    mockedGet.mockImplementationOnce(() => new Promise(() => {}));

    renderLogin();

    expect(await screen.findByTestId('recovery-loading')).toBeInTheDocument();
    expect(
      screen.queryByTestId('forgot-password-link'),
    ).not.toBeInTheDocument();
  });

  it('keeps Reset Loom visible inside tauri when the status query errors', async () => {
    // the operator's only escape from a wedged install is Reset Loom;
    // it must not depend on the backend that is already broken.
    mockedIsTauri = true;
    mockedGet.mockRejectedValue(new Error('backend unreachable'));

    renderLogin();

    expect(await screen.findByTestId('recovery-error')).toBeInTheDocument();
    expect(screen.getByTestId('factory-reset-link')).toBeInTheDocument();
    // forgot-password requires a backend round-trip, so it stays
    // hidden when we cannot confirm the profile.
    expect(
      screen.queryByTestId('forgot-password-link'),
    ).not.toBeInTheDocument();
  });

  it('shows the error message without Reset Loom in a plain web context', async () => {
    mockedIsTauri = false;
    mockedGet.mockRejectedValue(new Error('backend unreachable'));

    renderLogin();

    expect(await screen.findByTestId('recovery-error')).toBeInTheDocument();
    expect(screen.queryByTestId('factory-reset-link')).not.toBeInTheDocument();
  });
});
