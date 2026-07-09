import '@testing-library/jest-dom/vitest';
import 'jest-axe/extend-expect';

// cmdk (command palette) uses ResizeObserver and scrollIntoView,
// neither of which jsdom implements — stub them so component tests
// that render the palette don't throw.
class _ResizeObserver {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver ??=
  _ResizeObserver as unknown as typeof ResizeObserver;
if (typeof Element !== 'undefined' && !Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = (): void => {};
}
