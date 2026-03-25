import { useAuthStore } from '@/stores/auth-store';
import type { ApiError } from '@/types';

const BASE_URL = '/api/v1';

class ApiClientError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = 'ApiClientError';
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = useAuthStore.getState().token;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((options.headers as Record<string, string>) ?? {}),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (response.status === 401) {
    useAuthStore.getState().clearAuth();
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = (await response.json()) as ApiError;
      detail = body.detail ?? detail;
    } catch {
      // use statusText as fallback
    }
    throw new ApiClientError(response.status, detail);
  }

  // handle 204 no content
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export const apiClient = {
  get: <T>(path: string): Promise<T> =>
    request<T>(path, { method: 'GET' }),

  post: <T>(path: string, body?: unknown): Promise<T> =>
    request<T>(path, {
      method: 'POST',
      body: body ? JSON.stringify(body) : undefined,
    }),

  patch: <T>(path: string, body?: unknown): Promise<T> =>
    request<T>(path, {
      method: 'PATCH',
      body: body ? JSON.stringify(body) : undefined,
    }),

  delete: <T>(path: string): Promise<T> =>
    request<T>(path, { method: 'DELETE' }),
} as const;
