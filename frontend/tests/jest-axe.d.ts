/* eslint-disable @typescript-eslint/no-explicit-any */
declare module 'jest-axe' {
  import type { AxeResults } from 'axe-core';

  interface AxeOptions {
    rules?: Record<string, { enabled: boolean }>;
    [key: string]: any;
  }

  export function axe(
    html: Element | string,
    options?: AxeOptions,
  ): Promise<AxeResults>;

  export function toHaveNoViolations(): {
    message(): string;
    pass: boolean;
  };
}

declare module 'jest-axe/extend-expect' {}

interface CustomMatchers<R = unknown> {
  toHaveNoViolations(): R;
}

declare module 'vitest' {
  // eslint-disable-next-line @typescript-eslint/no-empty-interface
  interface Assertion<T = any> extends CustomMatchers<T> {}
  // eslint-disable-next-line @typescript-eslint/no-empty-interface
  interface AsymmetricMatchersContaining extends CustomMatchers {}
}
