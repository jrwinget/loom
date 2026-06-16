/// <reference types="@testing-library/jest-dom" />
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// hoisted bridge spies so the mock factory can close over them.
const { restartBackend, persistDataDirectory, pickDirectory } = vi.hoisted(
  () => ({
    restartBackend: vi.fn(async () => undefined),
    persistDataDirectory: vi.fn(async () => undefined),
    pickDirectory: vi.fn(async () => '/new-data-dir'),
  }),
);

vi.mock('@/lib/tauri-bridge', () => ({
  isTauri: true,
  pickDirectory,
  persistDataDirectory,
  restartBackend,
  factoryReset: vi.fn(async () => undefined),
  tauriDiskUsage: vi.fn(async () => null),
}));

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

import { FirstRunPage } from '@/routes/first-run';
import { apiClient } from '@/lib/api-client';

// untyped handles to sidestep the generic <T> signatures of apiClient.
const getMock = apiClient.get as unknown as ReturnType<typeof vi.fn>;
const postMock = apiClient.post as unknown as ReturnType<typeof vi.fn>;

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/first-run']}>
        <FirstRunPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('FirstRunPage data-dir ordering', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getMock.mockImplementation((path: string) => {
      if (path === '/first-run/status') {
        return Promise.resolve({
          firstRunRequired: true,
          deploymentProfile: 'lite',
          dataDir: '/old-data-dir',
        });
      }
      if (path === '/auth/me') {
        return Promise.resolve({
          id: 'u1',
          email: 'admin@example.com',
          displayName: 'Admin',
          role: 'admin',
        });
      }
      return Promise.reject(new Error(`unexpected GET ${path}`));
    });
    postMock.mockImplementation((path: string) => {
      if (path === '/storage/check') {
        return Promise.resolve({
          writable: true,
          writableReason: null,
          freeBytes: 1,
          totalBytes: 2,
          onSystemDrive: false,
          advisory: null,
          advisoryReason: null,
        });
      }
      if (path === '/first-run/complete') {
        return Promise.resolve({
          userId: 'u1',
          accessToken: 'tok',
          refreshToken: 'ref',
          passwordRecoveryCodes: ['a-b-c-d-e'],
        });
      }
      return Promise.reject(new Error(`unexpected POST ${path}`));
    });
  });

  it('restarts onto the chosen directory before creating the admin', async () => {
    const user = userEvent.setup();
    renderPage();

    await screen.findByTestId('first-run-data-dir');

    // pick a different directory -> validate + persist + select it.
    await user.click(
      screen.getByRole('button', { name: /pick different directory/i }),
    );
    await waitFor(() =>
      expect(screen.getByTestId('chosen-data-dir')).toHaveTextContent(
        '/new-data-dir',
      ),
    );

    // continue -> the sidecar must restart onto the new dir before the
    // admin step renders.
    await user.click(
      screen.getByRole('button', { name: /use this directory/i }),
    );

    const fullName = await screen.findByLabelText(/full name/i);
    expect(restartBackend).toHaveBeenCalledTimes(1);

    await user.type(fullName, 'Admin');
    await user.type(screen.getByLabelText(/^email$/i), 'admin@example.com');
    await user.type(
      screen.getByLabelText(/^password/i),
      'supersecret-123',
    );
    await user.type(
      screen.getByLabelText(/confirm password/i),
      'supersecret-123',
    );
    await user.click(
      screen.getByRole('button', { name: /create admin account/i }),
    );

    await waitFor(() =>
      expect(
        postMock.mock.calls.some(([p]) => p === '/first-run/complete'),
      ).toBe(true),
    );

    // the restart must have happened strictly before the admin insert.
    const completeIdx = postMock.mock.calls.findIndex(
      ([p]) => p === '/first-run/complete',
    );
    const completeOrder = postMock.mock.invocationCallOrder[completeIdx];
    const restartOrder = restartBackend.mock.invocationCallOrder[0];
    expect(restartOrder).toBeLessThan(completeOrder);
  });
});
