// regression guard for the missing `card` surface token. modals and
// every other `bg-card` surface render transparent when the token is
// undefined in either the tailwind theme or the backing css variables,
// so assert both halves stay in place. tailwind 4 is css-first: the
// theme lives in globals.css (@theme) rather than a js config, so
// both halves are asserted against the stylesheet.
import { readFileSync } from 'fs';
import { resolve } from 'path';
import { describe, expect, it } from 'vitest';

const css = readFileSync(
  resolve(__dirname, '../src/styles/globals.css'),
  'utf8',
);

describe('dark mode wiring', () => {
  it('uses the class strategy so the in-app toggle owns the theme', () => {
    // the custom variant keys dark: utilities off the .dark class,
    // not prefers-color-scheme — the media-query default would take
    // the theme away from the in-app toggle
    expect(css).toMatch(/@custom-variant dark \(&:is\(\.dark \*\)\)/);
  });

  it('sets color-scheme for both themes', () => {
    expect(css).toMatch(/color-scheme: light/);
    expect(css).toMatch(/color-scheme: dark/);
  });
});

describe('card surface token', () => {
  it('is registered in the theme with a foreground pair', () => {
    expect(css).toMatch(/--color-card: hsl\(var\(--card\)\)/);
    expect(css).toMatch(
      /--color-card-foreground: hsl\(var\(--card-foreground\)\)/,
    );
  });

  it('declares the backing css variables for light and dark themes', () => {
    // one declaration in :root, one in .dark (plus the @theme
    // registrations matched above)
    expect((css.match(/--card:/g) ?? []).length).toBeGreaterThanOrEqual(2);
    expect(
      (css.match(/--card-foreground:/g) ?? []).length,
    ).toBeGreaterThanOrEqual(2);
  });
});
