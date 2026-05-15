/// <reference types="@testing-library/jest-dom" />
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// FirstRunPage imports `isTauri` as a top-level const from
// tauri-bridge. mock the whole module so each test can flip the value
// to simulate desktop vs plain web.
let mockedIsTauri = false;

vi.mock('@/lib/tauri-bridge', () => ({
  get isTauri() {
    return mockedIsTauri;
  },
  factoryReset: vi.fn(),
  pickDirectory: vi.fn(),
  persistDataDirectory: vi.fn(),
  restartBackend: vi.fn(),
}));

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

import { apiClient } from '@/lib/api-client';
import { FirstRunPage } from '@/routes/first-run';

const mockedGet = vi.mocked(apiClient.get);

function renderFirstRun() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/first-run']}>
        <Routes>
          <Route path="/first-run" element={<FirstRunPage />} />
          <Route path="/" element={<div>Dashboard</div>} />
          <Route path="/login" element={<div>Login</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('FirstRunPage error escape hatch', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    mockedIsTauri = false;
  });

  it('shows Reset Loom inside tauri when the status query errors', async () => {
    // the operator gets redirected to /first-run after a factory
    // reset; if the sidecar is wedged we cannot strand them without
    // a recovery affordance.
    mockedIsTauri = true;
    mockedGet.mockRejectedValue(new Error('backend unreachable'));

    renderFirstRun();

    expect(await screen.findByTestId('first-run-error')).toBeInTheDocument();
    expect(screen.getByTestId('factory-reset-link')).toBeInTheDocument();
  });

  it('shows the error message without Reset Loom in plain web', async () => {
    mockedIsTauri = false;
    mockedGet.mockRejectedValue(new Error('backend unreachable'));

    renderFirstRun();

    expect(await screen.findByTestId('first-run-error')).toBeInTheDocument();
    expect(screen.queryByTestId('factory-reset-link')).not.toBeInTheDocument();
  });

  it('renders the onboarding form when status resolves', async () => {
    mockedGet.mockResolvedValueOnce({
      first_run_required: true,
      deployment_profile: 'lite',
      data_dir: '/home/user/.loom/data',
    });

    renderFirstRun();

    expect(await screen.findByText('Welcome to Loom')).toBeInTheDocument();
    expect(screen.queryByTestId('first-run-error')).not.toBeInTheDocument();
    expect(screen.queryByTestId('factory-reset-link')).not.toBeInTheDocument();
  });
});
