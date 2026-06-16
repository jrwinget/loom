import { useAuthStore } from '@/stores/auth-store';
import type { ApiError } from '@/types';

// in a tauri webview the document origin is tauri://localhost (or
// http://tauri.localhost on windows), so a relative '/api/v1' URL
// resolves against tauri's asset protocol handler, never the
// sidecar at 127.0.0.1:8000. detect the tauri runtime by probing
// window.__TAURI_INTERNALS__ at call time -- module-load detection
// would race the tauri bootstrap script in some bundlers. the CSP
// in desktop/src-tauri/tauri.conf.json whitelists this exact origin
// under connect-src.
const SIDECAR_ORIGIN = 'http://127.0.0.1:8000';
const API_PREFIX = '/api/v1';

export function getApiOrigin(): string {
  if (
    typeof window !== 'undefined' &&
    typeof (window as { __TAURI_INTERNALS__?: unknown }).__TAURI_INTERNALS__ !==
      'undefined'
  ) {
    return `${SIDECAR_ORIGIN}${API_PREFIX}`;
  }
  return API_PREFIX;
}

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

export function getCsrfToken(): string | null {
  const match = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/);
  return match ? decodeURIComponent(match[1]) : null;
}

const MUTATING_METHODS = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

// the desktop webview reuses an idle keep-alive socket for the submit
// POST after the initial GET (/first-run/status). once the sidecar
// closes that socket the reused-socket write fails at the transport
// layer and fetch rejects with a TypeError -- "Load failed" in WebKit.
// a transport reject means no HTTP response was received, so the
// request was never processed by the server: replaying it on a fresh
// connection is safe even for a POST (and /first-run/complete is
// additionally idempotent -- 201 then 409). an ApiClientError is only
// ever thrown AFTER a response arrives, so HTTP 4xx/5xx are never
// retried here.
const MAX_TRANSPORT_RETRIES = 2;
const RETRY_BASE_DELAY_MS = 150;

function isTransportError(err: unknown): boolean {
  return err instanceof TypeError;
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = useAuthStore.getState().token;
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...((options.headers as Record<string, string>) ?? {}),
  };

  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const method = (options.method ?? 'GET').toUpperCase();
  if (MUTATING_METHODS.has(method)) {
    const csrf = getCsrfToken();
    if (csrf) {
      headers['X-CSRF-Token'] = csrf;
    }
  }

  const url = `${getApiOrigin()}${path}`;
  let response: Response;
  for (let attempt = 0; ; attempt++) {
    try {
      response = await fetch(url, { ...options, headers });
      break;
    } catch (err) {
      // retry only a transport reject (the request was never
      // processed); exhausted attempts and non-transport errors
      // propagate unchanged.
      if (attempt < MAX_TRANSPORT_RETRIES && isTransportError(err)) {
        await sleep(RETRY_BASE_DELAY_MS * (attempt + 1));
        continue;
      }
      throw err;
    }
  }

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
  get: <T>(path: string): Promise<T> => request<T>(path, { method: 'GET' }),

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

  put: <T>(path: string, body?: unknown): Promise<T> =>
    request<T>(path, {
      method: 'PUT',
      body: body ? JSON.stringify(body) : undefined,
    }),

  delete: <T>(path: string, data?: unknown): Promise<T> =>
    request<T>(path, {
      method: 'DELETE',
      body: data ? JSON.stringify(data) : undefined,
    }),
} as const;
