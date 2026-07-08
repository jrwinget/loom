// regression guard for the missing `card` surface token. modals and
// every other `bg-card` surface render transparent when the token is
// undefined in either the tailwind theme or the backing css variables,
// so assert both halves stay in place.
import { readFileSync } from 'fs';
import { resolve } from 'path';
import { describe, expect, it } from 'vitest';
import tailwindConfig from '../tailwind.config';

describe('card surface token', () => {
  it('is registered in the tailwind theme with a foreground pair', () => {
    const colors = (tailwindConfig.theme?.extend?.colors ?? {}) as Record<
      string,
      unknown
    >;
    const card = colors.card as Record<string, unknown> | undefined;

    expect(card).toBeDefined();
    expect(card?.DEFAULT).toBe('hsl(var(--card))');
    expect(card?.foreground).toBe('hsl(var(--card-foreground))');
  });

  it('declares the backing css variables for light and dark themes', () => {
    const css = readFileSync(
      resolve(__dirname, '../src/styles/globals.css'),
      'utf8',
    );

    // one declaration in :root, one in .dark
    expect((css.match(/--card:/g) ?? []).length).toBeGreaterThanOrEqual(2);
    expect(
      (css.match(/--card-foreground:/g) ?? []).length,
    ).toBeGreaterThanOrEqual(2);
  });
});
