import { renderHook } from '@testing-library/react';
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest';
import { useKeyboardShortcut } from '@/hooks/use-keyboard';

// mock hotkeys-js
const mockBind = vi.fn();
const mockUnbind = vi.fn();

vi.mock('hotkeys-js', () => {
  const hotkeys = (
    key: string,
    handler: (e: KeyboardEvent) => void,
  ) => {
    mockBind(key, handler);
  };
  hotkeys.unbind = (key: string) => {
    mockUnbind(key);
  };
  return { default: hotkeys };
});

describe('useKeyboardShortcut', () => {
  beforeEach(() => {
    mockBind.mockClear();
    mockUnbind.mockClear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('registers keydown handler on mount', () => {
    const callback = vi.fn();
    renderHook(() => useKeyboardShortcut('ctrl+s', callback));

    expect(mockBind).toHaveBeenCalledWith(
      'ctrl+s',
      expect.any(Function),
    );
  });

  it('removes handler on unmount', () => {
    const callback = vi.fn();
    const { unmount } = renderHook(() =>
      useKeyboardShortcut('ctrl+s', callback),
    );

    unmount();

    expect(mockUnbind).toHaveBeenCalledWith('ctrl+s');
  });

  it('calls callback when matching key handler fires', () => {
    const callback = vi.fn();
    renderHook(() => useKeyboardShortcut('ctrl+s', callback));

    // extract the handler that was registered
    const handler = mockBind.mock.calls[0][1] as (
      e: KeyboardEvent,
    ) => void;
    const fakeEvent = {
      preventDefault: vi.fn(),
    } as unknown as KeyboardEvent;

    handler(fakeEvent);

    expect(fakeEvent.preventDefault).toHaveBeenCalled();
    expect(callback).toHaveBeenCalledTimes(1);
  });

  it('does not call callback for different key bindings', () => {
    const callbackA = vi.fn();
    const callbackB = vi.fn();

    renderHook(() => useKeyboardShortcut('ctrl+s', callbackA));
    renderHook(() => useKeyboardShortcut('ctrl+z', callbackB));

    // fire only the first handler
    const handlerA = mockBind.mock.calls[0][1] as (
      e: KeyboardEvent,
    ) => void;
    const fakeEvent = {
      preventDefault: vi.fn(),
    } as unknown as KeyboardEvent;

    handlerA(fakeEvent);

    expect(callbackA).toHaveBeenCalledTimes(1);
    expect(callbackB).not.toHaveBeenCalled();
  });

  it('supports modifier key combinations', () => {
    const callback = vi.fn();
    renderHook(() =>
      useKeyboardShortcut('ctrl+shift+alt+k', callback),
    );

    expect(mockBind).toHaveBeenCalledWith(
      'ctrl+shift+alt+k',
      expect.any(Function),
    );
  });

  it('rebinds when key string changes', () => {
    const callback = vi.fn();
    const { rerender } = renderHook(
      ({ key }: { key: string }) =>
        useKeyboardShortcut(key, callback),
      { initialProps: { key: 'ctrl+s' } },
    );

    expect(mockBind).toHaveBeenCalledTimes(1);
    expect(mockBind).toHaveBeenCalledWith(
      'ctrl+s',
      expect.any(Function),
    );

    rerender({ key: 'ctrl+d' });

    // unbinds old, binds new
    expect(mockUnbind).toHaveBeenCalledWith('ctrl+s');
    expect(mockBind).toHaveBeenCalledWith(
      'ctrl+d',
      expect.any(Function),
    );
  });
});
