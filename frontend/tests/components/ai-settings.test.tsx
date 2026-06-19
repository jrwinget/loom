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

function wrapper(): React.FC<{ children: React.ReactNode }> {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }) =>
    createElement(QueryClientProvider, { client: qc }, children);
}

beforeEach(() => {
  vi.clearAllMocks();
  mockedGet.mockResolvedValue({
    transcriptionEngine: 'local',
    apiBaseUrl: 'https://api.openai.com/v1',
    transcriptionModel: 'whisper-1',
    apiKeySet: false,
  });
});

describe('AiSettingsPage', () => {
  it('loads current settings from /settings/ai', async () => {
    render(<AiSettingsPage />, { wrapper: wrapper() });
    await waitFor(() =>
      expect(mockedGet).toHaveBeenCalledWith('/settings/ai'),
    );
  });

  it('saves a cloud config as a snake_case PUT body', async () => {
    mockedPut.mockResolvedValue({
      transcriptionEngine: 'cloud',
      apiBaseUrl: 'https://api.openai.com/v1',
      transcriptionModel: 'whisper-1',
      apiKeySet: true,
    });
    const { container } = render(<AiSettingsPage />, { wrapper: wrapper() });
    // the form only renders once settings load
    await screen.findByText('On-device');

    const cloud = container.querySelector(
      'input[value="cloud"]',
    ) as HTMLInputElement;
    fireEvent.click(cloud);
    fireEvent.change(screen.getByPlaceholderText('sk-…'), {
      target: { value: 'sk-test' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() =>
      expect(mockedPut).toHaveBeenCalledWith(
        '/settings/ai',
        expect.objectContaining({
          transcription_engine: 'cloud',
          api_key: 'sk-test',
        }),
      ),
    );
  });
});
