import { describe, expect, it } from 'vitest';
import { getCsrfToken } from '@/lib/api-client';

describe('getCsrfToken', () => {
  function withCookie(cookie: string, fn: () => void) {
    Object.defineProperty(document, 'cookie', {
      value: cookie,
      writable: true,
      configurable: true,
    });
    try {
      fn();
    } finally {
      Object.defineProperty(document, 'cookie', {
        value: '',
        writable: true,
        configurable: true,
      });
    }
  }

  it('returns null when no cookies are set', () => {
    withCookie('', () => {
      expect(getCsrfToken()).toBeNull();
    });
  });

  it('returns the value for the csrf_token cookie', () => {
    withCookie('csrf_token=abc123; session=xyz', () => {
      expect(getCsrfToken()).toBe('abc123');
    });
  });

  it('handles base64 values with embedded equals signs', () => {
    withCookie('csrf_token=YWJj%3Ddef%3D%3D; other=val', () => {
      expect(getCsrfToken()).toBe('YWJj=def==');
    });
  });

  it('returns null when csrf_token is missing', () => {
    withCookie('session=xyz; theme=dark', () => {
      expect(getCsrfToken()).toBeNull();
    });
  });

  it('does not match partial cookie names', () => {
    withCookie('my_csrf_token=bad; csrf_token=good', () => {
      expect(getCsrfToken()).toBe('good');
    });
  });

  it('decodes uri-encoded values', () => {
    withCookie('csrf_token=hello%20world', () => {
      expect(getCsrfToken()).toBe('hello world');
    });
  });
});
