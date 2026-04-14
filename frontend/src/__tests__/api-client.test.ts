import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/stores/auth-store', () => ({
  useAuthStore: {
    getState: () => ({ token: 'test-token', clearAuth: vi.fn() }),
  },
}));

import { apiClient } from '@/lib/api-client';

describe('apiClient', () => {
  beforeEach(() => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('delete()', () => {
    it('sends body when provided', async () => {
      await apiClient.delete('/items/1', { reason: 'test' });

      expect(fetch).toHaveBeenCalledWith(
        '/api/v1/items/1',
        expect.objectContaining({
          method: 'DELETE',
          body: JSON.stringify({ reason: 'test' }),
        }),
      );
    });

    it('works without body', async () => {
      await apiClient.delete('/items/1');

      expect(fetch).toHaveBeenCalledWith(
        '/api/v1/items/1',
        expect.objectContaining({
          method: 'DELETE',
          body: undefined,
        }),
      );
    });
  });

  describe('put()', () => {
    it('sends body correctly', async () => {
      await apiClient.put('/items/1', { name: 'updated' });

      expect(fetch).toHaveBeenCalledWith(
        '/api/v1/items/1',
        expect.objectContaining({
          method: 'PUT',
          body: JSON.stringify({ name: 'updated' }),
        }),
      );
    });

    it('works without body', async () => {
      await apiClient.put('/items/1');

      expect(fetch).toHaveBeenCalledWith(
        '/api/v1/items/1',
        expect.objectContaining({
          method: 'PUT',
          body: undefined,
        }),
      );
    });
  });
});
