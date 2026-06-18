import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// a stable clearAuth spy so the 401 path can be asserted. hoisted so
// the vi.mock factory (which is hoisted above imports) can close over
// it without a temporal-dead-zone error.
const { clearAuth } = vi.hoisted(() => ({ clearAuth: vi.fn() }));

vi.mock('@/stores/auth-store', () => ({
  useAuthStore: {
    getState: () => ({ token: null, clearAuth }),
  },
}));

import { apiClient } from '@/lib/api-client';

function jsonResponse(body: unknown, status: number): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('apiClient transport-retry', () => {
  beforeEach(() => {
    // fake timers so the 150ms/300ms backoff does not slow the suite.
    vi.useFakeTimers();
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('retries a transport reject on a fresh connection and resolves', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockRejectedValueOnce(new TypeError('Load failed'))
      .mockResolvedValueOnce(jsonResponse({ ok: true }, 200));

    const promise = apiClient.post('/first-run/complete', { admin_email: 'a' });
    await vi.runAllTimersAsync();

    await expect(promise).resolves.toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it('caps retries at two and then propagates the transport error', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockRejectedValue(new TypeError('Load failed'));

    const promise = apiClient.get('/first-run/status');
    // attach the rejection handler before draining timers so the
    // pending rejection is never reported as unhandled.
    const rejection = expect(promise).rejects.toThrow('Load failed');
    await vi.runAllTimersAsync();
    await rejection;

    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it('does not retry an HTTP 409 conflict', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(
        jsonResponse({ detail: 'first-run already completed' }, 409),
      );

    await expect(
      apiClient.post('/first-run/complete', {}),
    ).rejects.toMatchObject({ status: 409 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('does not retry an HTTP 500 server error', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse({ detail: 'boom' }, 500));

    await expect(apiClient.get('/health')).rejects.toMatchObject({
      status: 500,
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('clears auth on 401 without retrying', async () => {
    const fetchMock = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValue(jsonResponse({ detail: 'unauthorized' }, 401));

    await expect(apiClient.get('/auth/me')).rejects.toMatchObject({
      status: 401,
    });
    expect(clearAuth).toHaveBeenCalledTimes(1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
