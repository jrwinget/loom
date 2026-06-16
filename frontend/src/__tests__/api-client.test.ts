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

  describe('response key transform', () => {
    function mockJson(body: unknown): void {
      vi.spyOn(globalThis, 'fetch').mockResolvedValue(
        new Response(JSON.stringify(body), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      );
    }

    it('camelizes snake_case keys in nested objects and arrays', async () => {
      mockJson({
        access_token: 'a',
        items: [{ asset_count: 2, created_at: 't' }],
      });

      const res = await apiClient.get('/x');

      expect(res).toEqual({
        accessToken: 'a',
        items: [{ assetCount: 2, createdAt: 't' }],
      });
    });

    it('preserves inner keys of opaque blobs', async () => {
      mockJson({
        manifest_data: { claim_generator: 'c2pa', nested: { a_b: 1 } },
        detail: { codes_remaining: 3 },
        reasoning: { time_proximity: { score: 0.9 } },
      });

      const res = await apiClient.get('/x');

      expect(res).toEqual({
        manifestData: { claim_generator: 'c2pa', nested: { a_b: 1 } },
        detail: { codes_remaining: 3 },
        reasoning: { time_proximity: { score: 0.9 } },
      });
    });

    it('passes null and primitive values through unchanged', async () => {
      mockJson({ a_b: null, c_d: 5, e_f: 'x', g_h: [1, 2] });

      const res = await apiClient.get('/x');

      expect(res).toEqual({ aB: null, cD: 5, eF: 'x', gH: [1, 2] });
    });

    it('does not transform the request body', async () => {
      mockJson({ ok: true });

      await apiClient.post('/x', { admin_email: 'a@b.co', user_id: '1' });

      expect(fetch).toHaveBeenCalledWith(
        '/api/v1/x',
        expect.objectContaining({
          body: JSON.stringify({ admin_email: 'a@b.co', user_id: '1' }),
        }),
      );
    });
  });
});
