/// <reference types="@testing-library/jest-dom" />
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { axe } from 'jest-axe';
import { createElement } from 'react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api-client', () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));
vi.mock('@/stores/toast-store', () => ({
  useToastStore: { getState: () => ({ addToast: vi.fn() }) },
}));

import { apiClient } from '@/lib/api-client';
import { StorageAdvisory } from '@/components/asset/storage-advisory';

const mockedGet = vi.mocked(apiClient.get);
const mockedPost = vi.mocked(apiClient.post);

const usageWire = {
  dataDir: '/srv/loom',
  freeBytes: 1_000_000,
  totalBytes: 10_000_000,
  originalsBytes: 0,
  derivativesBytes: 0,
  dbBytes: 0,
  logsBytes: 0,
  assetCount: 0,
  onSystemDrive: false,
};

function setProfile(profile: 'server' | 'lite'): void {
  mockedGet.mockImplementation((path: string) => {
    if (path === '/first-run/status') {
      return Promise.resolve({
        firstRunRequired: false,
        deploymentProfile: profile,
      });
    }
    if (path === '/storage/usage') {
      return Promise.resolve(usageWire);
    }
    return Promise.reject(new Error(`unexpected GET ${path}`));
  });
}

function renderAdvisory(): { container: HTMLElement } {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const file = new File([new Uint8Array(1024)], 'clip.mp4');
  return render(
    createElement(
      QueryClientProvider,
      { client: qc },
      createElement(
        MemoryRouter,
        null,
        createElement(StorageAdvisory, { selectedFiles: [file] }),
      ),
    ),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('StorageAdvisory', () => {
  it('renders nothing on a server-profile install', async () => {
    setProfile('server');

    renderAdvisory();

    await waitFor(() =>
      expect(mockedGet).toHaveBeenCalledWith('/first-run/status'),
    );
    expect(screen.queryByTestId('storage-advisory')).not.toBeInTheDocument();
  });

  it('renders nothing when the storage check is not a warning', async () => {
    setProfile('lite');
    mockedPost.mockResolvedValue({
      writable: true,
      writableReason: null,
      freeBytes: 1_000_000,
      totalBytes: 10_000_000,
      onSystemDrive: false,
      advisory: 'ok',
      advisoryReason: null,
    } as never);

    renderAdvisory();

    await waitFor(() => expect(mockedPost).toHaveBeenCalled());
    expect(screen.queryByTestId('storage-advisory')).not.toBeInTheDocument();
  });

  it('warns with a reason and a settings link when free space is low', async () => {
    setProfile('lite');
    mockedPost.mockResolvedValue({
      writable: true,
      writableReason: null,
      freeBytes: 100,
      totalBytes: 10_000_000,
      onSystemDrive: false,
      advisory: 'warning',
      advisoryReason: 'Less than 2 GB free',
    } as never);

    renderAdvisory();

    await waitFor(() =>
      expect(screen.getByTestId('storage-advisory')).toBeInTheDocument(),
    );
    expect(screen.getByText('Less than 2 GB free')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /change storage in settings/i }),
    ).toBeInTheDocument();
  });

  it('has no accessibility violations when the warning is shown', async () => {
    setProfile('lite');
    mockedPost.mockResolvedValue({
      writable: true,
      writableReason: null,
      freeBytes: 100,
      totalBytes: 10_000_000,
      onSystemDrive: false,
      advisory: 'warning',
      advisoryReason: 'Less than 2 GB free',
    } as never);

    const { container } = renderAdvisory();

    await waitFor(() =>
      expect(screen.getByTestId('storage-advisory')).toBeInTheDocument(),
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
