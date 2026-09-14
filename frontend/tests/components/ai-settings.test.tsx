/// <reference types="@testing-library/jest-dom" />
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api-client', () => ({
  apiClient: { get: vi.fn(), put: vi.fn() },
}));
vi.mock('@/stores/toast-store', () => ({
  useToastStore: { getState: () => ({ addToast: vi.fn() }) },
}));

import { apiClient } from '@/lib/api-client';
import { AiSettingsPage } from '@/routes/settings/ai';

const mockedGet = vi.mocked(apiClient.get);
const mockedPut = vi.mocked(apiClient.put);

const PROVIDERS = [
  {
    id: 'oss',
    label: 'Open-source (self-hosted)',
    group: 'oss',
    models: [{ id: 'whisper-large-v3', label: 'Whisper large-v3' }],
    requiresApiKey: false,
    baseUrl: '',
    baseUrlEditable: true,
    available: true,
    note: 'self-host',
  },
  {
    id: 'custom',
    label: 'Custom',
    group: 'custom',
    models: [],
    requiresApiKey: true,
    baseUrl: '',
    baseUrlEditable: true,
    available: true,
    note: '',
  },
];

const DEFAULT_SETTINGS = {
  transcriptionEngine: 'local',
  provider: '',
  apiBaseUrl: 'https://api.openai.com/v1',
  transcriptionModel: 'whisper-1',
  whisperModel: 'base',
  apiKeySet: false,
  providerAvailable: true,
  keyDecryptable: true,
};

function wrapper(): React.FC<{ children: React.ReactNode }> {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }) =>
    createElement(QueryClientProvider, { client: qc }, children);
}

function mockGetResponses(
  settingsOverride: Partial<typeof DEFAULT_SETTINGS> = {},
): void {
  mockedGet.mockImplementation((path: string) => {
    if (path === '/settings/ai/providers') {
      return Promise.resolve({ providers: PROVIDERS }) as never;
    }
    if (path === '/settings/engines') {
      return Promise.resolve({ engines: {}, models: [] }) as never;
    }
    return Promise.resolve({
      ...DEFAULT_SETTINGS,
      ...settingsOverride,
    }) as never;
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mockGetResponses();
});

describe('AiSettingsPage', () => {
  it('loads settings and the provider catalog', async () => {
    render(<AiSettingsPage />, { wrapper: wrapper() });
    await screen.findByText('On-device');
    expect(mockedGet).toHaveBeenCalledWith('/settings/ai');
    expect(mockedGet).toHaveBeenCalledWith('/settings/ai/providers');
  });

  it('only offers self-hosted and custom providers', async () => {
    render(<AiSettingsPage />, { wrapper: wrapper() });
    await screen.findByText('On-device');

    fireEvent.click(screen.getByRole('radio', { name: /cloud/i }));
    const options = screen
      .getAllByRole('option')
      .map((o) => (o as HTMLOptionElement).value)
      .filter((v) => v !== '');
    expect(options).toEqual(['oss', 'custom']);
  });

  it('lets a self-hosted provider set a free-form base url, keyless', async () => {
    mockedPut.mockResolvedValue({} as never);
    render(<AiSettingsPage />, { wrapper: wrapper() });
    await screen.findByText('On-device');

    fireEvent.click(screen.getByRole('radio', { name: /cloud/i }));
    fireEvent.change(screen.getByTestId('provider-select'), {
      target: { value: 'oss' },
    });
    // oss has a fixed model catalog and an editable base url
    expect(screen.getByTestId('model-select')).toHaveValue(
      'whisper-large-v3',
    );
    const baseUrl = screen.getByTestId('base-url-input');
    expect(baseUrl).not.toHaveAttribute('readonly');
    fireEvent.change(baseUrl, {
      target: { value: 'https://my-lan-box.example/v1' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() =>
      expect(mockedPut).toHaveBeenCalledWith(
        '/settings/ai',
        expect.objectContaining({
          provider: 'oss',
          transcription_model: 'whisper-large-v3',
          api_base_url: 'https://my-lan-box.example/v1',
        }),
      ),
    );
  });

  it('lets a custom provider set a free-form model and base url', async () => {
    mockedPut.mockResolvedValue({} as never);
    render(<AiSettingsPage />, { wrapper: wrapper() });
    await screen.findByText('On-device');

    fireEvent.click(screen.getByRole('radio', { name: /cloud/i }));
    fireEvent.change(screen.getByTestId('provider-select'), {
      target: { value: 'custom' },
    });
    const baseUrl = screen.getByTestId('base-url-input');
    expect(baseUrl).not.toHaveAttribute('readonly');
    fireEvent.change(baseUrl, {
      target: { value: 'https://my-host/v1' },
    });
    fireEvent.change(screen.getByTestId('model-input'), {
      target: { value: 'my-model' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() =>
      expect(mockedPut).toHaveBeenCalledWith(
        '/settings/ai',
        expect.objectContaining({
          provider: 'custom',
          transcription_model: 'my-model',
          api_base_url: 'https://my-host/v1',
        }),
      ),
    );
  });

  it('shows a warning when the configured provider is no longer supported', async () => {
    mockGetResponses({
      transcriptionEngine: 'cloud',
      provider: 'openai',
      providerAvailable: false,
    });
    render(<AiSettingsPage />, { wrapper: wrapper() });
    await screen.findByTestId('provider-unavailable-banner');
  });

  it('shows a warning when the stored key cannot be decrypted', async () => {
    mockGetResponses({
      transcriptionEngine: 'cloud',
      provider: 'custom',
      apiKeySet: true,
      keyDecryptable: false,
    });
    render(<AiSettingsPage />, { wrapper: wrapper() });
    await screen.findByTestId('key-undecryptable-banner');
  });

  it('shows no warning banner for a healthy configuration', async () => {
    mockGetResponses({
      transcriptionEngine: 'cloud',
      provider: 'oss',
    });
    render(<AiSettingsPage />, { wrapper: wrapper() });
    await screen.findByText('On-device');
    expect(
      screen.queryByTestId('provider-unavailable-banner'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByTestId('key-undecryptable-banner'),
    ).not.toBeInTheDocument();
  });
});
