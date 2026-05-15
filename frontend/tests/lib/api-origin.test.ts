import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/stores/auth-store', () => ({
  useAuthStore: {
    getState: () => ({ token: null, clearAuth: vi.fn() }),
  },
}));

import { apiClient, getApiOrigin } from '@/lib/api-client';

function setTauriInternals(present: boolean): void {
  if (present) {
    (window as unknown as { __TAURI_INTERNALS__: unknown }).__TAURI_INTERNALS__ =
      { invoke: vi.fn() };
  } else {
    delete (window as unknown as { __TAURI_INTERNALS__?: unknown })
      .__TAURI_INTERNALS__;
  }
}

describe('getApiOrigin', () => {
  afterEach(() => {
    setTauriInternals(false);
  });

  it('returns the loopback sidecar origin inside tauri', () => {
    setTauriInternals(true);
    expect(getApiOrigin()).toBe('http://127.0.0.1:8000/api/v1');
  });

  it('returns the relative prefix in a plain web context', () => {
    setTauriInternals(false);
    expect(getApiOrigin()).toBe('/api/v1');
  });
});

describe('apiClient base url', () => {
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
  });

  afterEach(() => {
    setTauriInternals(false);
    vi.restoreAllMocks();
  });

  it('prepends the loopback origin when running inside tauri', async () => {
    setTauriInternals(true);
    await apiClient.get('/health');
    expect(fetch).toHaveBeenCalledWith(
      'http://127.0.0.1:8000/api/v1/health',
      expect.any(Object),
    );
  });

  it('uses the relative prefix when not running inside tauri', async () => {
    setTauriInternals(false);
    await apiClient.get('/health');
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/health',
      expect.any(Object),
    );
  });
});
