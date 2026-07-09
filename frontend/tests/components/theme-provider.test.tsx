/// <reference types="@testing-library/jest-dom" />
import { act, render } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ThemeProvider } from '@/components/layout/theme-provider';
import { resolveTheme, useThemeStore } from '@/stores/theme-store';

type Listener = (e: { matches: boolean }) => void;

function mockMatchMedia(initialDark: boolean): {
  setSystemDark: (dark: boolean) => void;
} {
  let matches = initialDark;
  const listeners = new Set<Listener>();
  vi.stubGlobal(
    'matchMedia',
    vi.fn().mockImplementation((query: string) => ({
      get matches() {
        return matches;
      },
      media: query,
      addEventListener: (_: string, cb: Listener) => listeners.add(cb),
      removeEventListener: (_: string, cb: Listener) => listeners.delete(cb),
    })),
  );
  return {
    setSystemDark: (dark: boolean) => {
      matches = dark;
      listeners.forEach((cb) => cb({ matches: dark }));
    },
  };
}

describe('resolveTheme', () => {
  it.each([
    ['light', false, 'light'],
    ['light', true, 'light'],
    ['dark', false, 'dark'],
    ['system', true, 'dark'],
    ['system', false, 'light'],
  ] as const)(
    'preference %s with systemDark=%s -> %s',
    (preference, systemDark, expected) => {
      expect(resolveTheme(preference, systemDark)).toBe(expected);
    },
  );
});

describe('ThemeProvider', () => {
  beforeEach(() => {
    document.documentElement.classList.remove('dark');
    useThemeStore.setState({ theme: 'system' });
  });

  it('applies the dark class for an explicit dark preference', () => {
    mockMatchMedia(false);
    useThemeStore.setState({ theme: 'dark' });

    render(<ThemeProvider>x</ThemeProvider>);

    expect(document.documentElement.classList.contains('dark')).toBe(true);
  });

  it('removes the dark class for an explicit light preference', () => {
    mockMatchMedia(true);
    document.documentElement.classList.add('dark');
    useThemeStore.setState({ theme: 'light' });

    render(<ThemeProvider>x</ThemeProvider>);

    expect(document.documentElement.classList.contains('dark')).toBe(false);
  });

  it('follows the os live under the system preference', () => {
    const media = mockMatchMedia(false);

    render(<ThemeProvider>x</ThemeProvider>);
    expect(document.documentElement.classList.contains('dark')).toBe(false);

    act(() => media.setSystemDark(true));
    expect(document.documentElement.classList.contains('dark')).toBe(true);

    act(() => media.setSystemDark(false));
    expect(document.documentElement.classList.contains('dark')).toBe(false);
  });

  it('switches when the stored preference changes', () => {
    mockMatchMedia(false);
    render(<ThemeProvider>x</ThemeProvider>);

    act(() => useThemeStore.setState({ theme: 'dark' }));
    expect(document.documentElement.classList.contains('dark')).toBe(true);

    act(() => useThemeStore.setState({ theme: 'light' }));
    expect(document.documentElement.classList.contains('dark')).toBe(false);
  });
});
