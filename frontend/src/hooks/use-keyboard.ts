import hotkeys from 'hotkeys-js';
import { useEffect } from 'react';

export function useKeyboardShortcut(
  key: string,
  callback: () => void,
  deps: unknown[] = [],
): void {
  useEffect(() => {
    hotkeys(key, (event) => {
      event.preventDefault();
      callback();
    });

    return () => {
      hotkeys.unbind(key);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, ...deps]);
}
