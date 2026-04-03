import { describe, expect, it } from 'vitest';
import { getCookieValue } from '@/lib/api-client';

describe('getCookieValue', () => {
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
      expect(getCookieValue('csrf_token')).toBeNull();
    });
  });

  it('returns the value for an existing cookie', () => {
    withCookie('csrf_token=abc123; session=xyz', () => {
      expect(getCookieValue('csrf_token')).toBe('abc123');
    });
  });

  it('handles base64 values with embedded equals signs', () => {
    withCookie('csrf_token=YWJj=def==; other=val', () => {
      expect(getCookieValue('csrf_token')).toBe('YWJj=def==');
    });
  });

  it('returns null for a missing cookie name', () => {
    withCookie('session=xyz; theme=dark', () => {
      expect(getCookieValue('csrf_token')).toBeNull();
    });
  });

  it('does not match partial cookie names', () => {
    withCookie('my_csrf_token=bad; csrf_token=good', () => {
      expect(getCookieValue('csrf_token')).toBe('good');
    });
  });

  it('decodes uri-encoded values', () => {
    withCookie('csrf_token=hello%20world', () => {
      expect(getCookieValue('csrf_token')).toBe('hello world');
    });
  });
});
