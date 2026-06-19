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
    id: 'openai',
    label: 'OpenAI',
    group: 'frontier',
    models: [
      { id: 'gpt-4o-transcribe', label: 'GPT-4o Transcribe' },
      { id: 'whisper-1', label: 'Whisper v2' },
    ],
    requiresApiKey: true,
    baseUrl: 'https://api.openai.com/v1',
    baseUrlEditable: false,
    available: true,
    note: '',
  },
  {
    id: 'anthropic',
    label: 'Anthropic',
    group: 'frontier',
    models: [],
    requiresApiKey: true,
    baseUrl: '',
    baseUrlEditable: false,
    available: false,
    note: 'no audio input yet',
  },
  {
    id: 'oss',
    label: 'Open-source',
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

function wrapper(): React.FC<{ children: React.ReactNode }> {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }) =>
    createElement(QueryClientProvider, { client: qc }, children);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedGet.mockImplementation((path: string) => {
    if (path === '/settings/ai/providers') {
      return Promise.resolve({ providers: PROVIDERS }) as never;
    }
    return Promise.resolve({
      transcriptionEngine: 'local',
      provider: '',
      apiBaseUrl: 'https://api.openai.com/v1',
      transcriptionModel: 'whisper-1',
      apiKeySet: false,
    }) as never;
  });
});

describe('AiSettingsPage', () => {
  it('loads settings and the provider catalog', async () => {
    render(<AiSettingsPage />, { wrapper: wrapper() });
    await screen.findByText('On-device');
    expect(mockedGet).toHaveBeenCalledWith('/settings/ai');
    expect(mockedGet).toHaveBeenCalledWith('/settings/ai/providers');
  });

  it('cascades a frontier provider to its models and saves snake_case', async () => {
    mockedPut.mockResolvedValue({
      transcriptionEngine: 'cloud',
      provider: 'openai',
      apiBaseUrl: 'https://api.openai.com/v1',
      transcriptionModel: 'gpt-4o-transcribe',
      apiKeySet: true,
    } as never);
    render(<AiSettingsPage />, { wrapper: wrapper() });
    await screen.findByText('On-device');

    fireEvent.click(screen.getByRole('radio', { name: /cloud/i }));
    // save is gated until a provider is chosen
    expect(screen.getByRole('button', { name: /save/i })).toBeDisabled();

    fireEvent.change(screen.getByTestId('provider-select'), {
      target: { value: 'openai' },
    });
    // model dropdown is now populated from the provider's catalog
    expect(screen.getByTestId('model-select')).toHaveValue('gpt-4o-transcribe');
    fireEvent.change(screen.getByPlaceholderText('sk-…'), {
      target: { value: 'sk-test' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() =>
      expect(mockedPut).toHaveBeenCalledWith('/settings/ai', {
        transcription_engine: 'cloud',
        provider: 'openai',
        transcription_model: 'gpt-4o-transcribe',
        api_key: 'sk-test',
      }),
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
    // custom exposes a free-form model field and an editable base url
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

  it('locks the base url for a hosted provider', async () => {
    render(<AiSettingsPage />, { wrapper: wrapper() });
    await screen.findByText('On-device');

    fireEvent.click(screen.getByRole('radio', { name: /cloud/i }));
    fireEvent.change(screen.getByTestId('provider-select'), {
      target: { value: 'openai' },
    });
    const baseUrl = screen.getByTestId('base-url-input');
    expect(baseUrl).toHaveAttribute('readonly');
    expect(baseUrl).toHaveValue('https://api.openai.com/v1');
  });

  it('shows Anthropic as a disabled option', async () => {
    render(<AiSettingsPage />, { wrapper: wrapper() });
    await screen.findByText('On-device');

    fireEvent.click(screen.getByRole('radio', { name: /cloud/i }));
    const anthropic = screen.getByRole('option', {
      name: /Anthropic/,
    }) as HTMLOptionElement;
    expect(anthropic).toBeDisabled();
  });
});
