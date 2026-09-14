import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  useAiSettings,
  useAiProviders,
  useUpdateAiSettings,
  useTextGenSettings,
  useTextGenProviders,
  useUpdateTextGenSettings,
} from '@/hooks/use-ai-settings';
import type {
  AiSettings,
  AiProvider,
  TextGenSettings,
  TextGenProvider,
} from '@/hooks/use-ai-settings';

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn(),
    put: vi.fn(),
  },
}));

const addToast = vi.fn();
vi.mock('@/stores/toast-store', () => ({
  useToastStore: { getState: () => ({ addToast }) },
}));

const settings: AiSettings = {
  transcriptionEngine: 'whisper',
  provider: 'openai',
  apiBaseUrl: 'https://api.openai.com/v1',
  transcriptionModel: 'whisper-1',
  whisperModel: 'base',
  apiKeySet: true,
  providerAvailable: true,
  keyDecryptable: true,
};

function createWrapper(): ({
  children,
}: {
  children: React.ReactNode;
}) => React.ReactElement {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return ({ children }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useAiSettings', () => {
  it('fetches the ai settings from the settings endpoint', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.get).mockResolvedValueOnce(settings);

    const { result } = renderHook(() => useAiSettings(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(settings);
  });
});

describe('useAiProviders', () => {
  it('unwraps the providers array from the response envelope', async () => {
    const provider: AiProvider = {
      id: 'openai',
      label: 'OpenAI',
      group: 'cloud',
      models: [{ id: 'whisper-1', label: 'Whisper' }],
      requiresApiKey: true,
      baseUrl: 'https://api.openai.com/v1',
      baseUrlEditable: false,
      available: true,
      note: '',
    };
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.get).mockResolvedValueOnce({ providers: [provider] });

    const { result } = renderHook(() => useAiProviders(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([provider]);
  });
});

describe('useUpdateAiSettings', () => {
  it('sends the patch body verbatim to the settings endpoint', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.put).mockResolvedValueOnce(settings);

    const { result } = renderHook(() => useUpdateAiSettings(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({ provider: 'anthropic', api_key: 'secret' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(vi.mocked(apiClient.put)).toHaveBeenCalledWith('/settings/ai', {
      provider: 'anthropic',
      api_key: 'secret',
    });
  });

  it('shows a success toast after saving', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.put).mockResolvedValueOnce(settings);

    const { result } = renderHook(() => useUpdateAiSettings(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({ provider: 'openai' });

    await waitFor(() =>
      expect(addToast).toHaveBeenCalledWith({
        type: 'success',
        message: 'AI settings saved',
      }),
    );
  });

  it('shows an error toast with the failure message when saving fails', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.put).mockRejectedValueOnce(new Error('nope'));

    const { result } = renderHook(() => useUpdateAiSettings(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({ provider: 'openai' });

    await waitFor(() =>
      expect(addToast).toHaveBeenCalledWith({
        type: 'error',
        message: 'nope',
      }),
    );
  });
});

const textGenSettings: TextGenSettings = {
  enabled: false,
  provider: '',
  apiBaseUrl: '',
  model: '',
  apiKeySet: false,
  providerAvailable: true,
  keyDecryptable: true,
};

describe('useTextGenSettings', () => {
  it('fetches the text-generation settings from the settings endpoint', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.get).mockResolvedValueOnce(textGenSettings);

    const { result } = renderHook(() => useTextGenSettings(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(apiClient.get).toHaveBeenCalledWith('/settings/ai/text-generation');
    expect(result.current.data).toEqual(textGenSettings);
  });
});

describe('useTextGenProviders', () => {
  it('unwraps the providers array from the response envelope', async () => {
    const provider: TextGenProvider = {
      id: 'oss',
      label: 'Open-source (self-hosted)',
      group: 'oss',
      models: [{ id: 'gpt-oss-20b', label: 'gpt-oss-20b', contextWindow: 128000 }],
      requiresApiKey: false,
      baseUrl: '',
      baseUrlEditable: true,
      note: '',
    };
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.get).mockResolvedValueOnce({ providers: [provider] });

    const { result } = renderHook(() => useTextGenProviders(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(apiClient.get).toHaveBeenCalledWith(
      '/settings/ai/text-generation/providers',
    );
    expect(result.current.data).toEqual([provider]);
  });
});

describe('useUpdateTextGenSettings', () => {
  it('sends the patch body verbatim to the settings endpoint', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.put).mockResolvedValueOnce(textGenSettings);

    const { result } = renderHook(() => useUpdateTextGenSettings(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({ provider: 'custom', api_key: 'secret' });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(vi.mocked(apiClient.put)).toHaveBeenCalledWith(
      '/settings/ai/text-generation',
      { provider: 'custom', api_key: 'secret' },
    );
  });

  it('shows a success toast after saving', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.put).mockResolvedValueOnce(textGenSettings);

    const { result } = renderHook(() => useUpdateTextGenSettings(), {
      wrapper: createWrapper(),
    });
    result.current.mutate({ enabled: true });

    await waitFor(() =>
      expect(addToast).toHaveBeenCalledWith({
        type: 'success',
        message: 'Text-generation settings saved',
      }),
    );
  });
});
