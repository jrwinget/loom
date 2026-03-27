import { act, renderHook } from '@testing-library/react';
import {
  afterEach,
  beforeEach,
  describe,
  expect,
  it,
  vi,
} from 'vitest';
import {
  useNetworkStatus,
} from '@/hooks/use-network-status';

describe('useNetworkStatus', () => {
  let onLineSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    onLineSpy = vi.spyOn(navigator, 'onLine', 'get');
    onLineSpy.mockReturnValue(true);
  });

  afterEach(() => {
    onLineSpy.mockRestore();
  });

  it('reports online when navigator.onLine is true', () => {
    onLineSpy.mockReturnValue(true);
    const { result } = renderHook(() =>
      useNetworkStatus(),
    );
    expect(result.current.isOnline).toBe(true);
    expect(result.current.wasOffline).toBe(false);
  });

  it('reports offline when navigator.onLine is false', () => {
    onLineSpy.mockReturnValue(false);
    const { result } = renderHook(() =>
      useNetworkStatus(),
    );
    expect(result.current.isOnline).toBe(false);
  });

  it('updates on offline event', () => {
    onLineSpy.mockReturnValue(true);
    const { result } = renderHook(() =>
      useNetworkStatus(),
    );

    act(() => {
      onLineSpy.mockReturnValue(false);
      window.dispatchEvent(new Event('offline'));
    });

    expect(result.current.isOnline).toBe(false);
  });

  it('sets wasOffline on online event', () => {
    onLineSpy.mockReturnValue(false);
    const { result } = renderHook(() =>
      useNetworkStatus(),
    );

    act(() => {
      onLineSpy.mockReturnValue(true);
      window.dispatchEvent(new Event('online'));
    });

    expect(result.current.isOnline).toBe(true);
    expect(result.current.wasOffline).toBe(true);
  });

  it('clears wasOffline on acknowledge', () => {
    onLineSpy.mockReturnValue(false);
    const { result } = renderHook(() =>
      useNetworkStatus(),
    );

    act(() => {
      onLineSpy.mockReturnValue(true);
      window.dispatchEvent(new Event('online'));
    });

    expect(result.current.wasOffline).toBe(true);

    act(() => {
      result.current.acknowledgeReconnection();
    });

    expect(result.current.wasOffline).toBe(false);
  });

  it('cleans up event listeners on unmount', () => {
    const addSpy = vi.spyOn(window, 'addEventListener');
    const removeSpy = vi.spyOn(
      window,
      'removeEventListener',
    );

    const { unmount } = renderHook(() =>
      useNetworkStatus(),
    );

    expect(addSpy).toHaveBeenCalledWith(
      'online',
      expect.any(Function),
    );
    expect(addSpy).toHaveBeenCalledWith(
      'offline',
      expect.any(Function),
    );

    unmount();

    expect(removeSpy).toHaveBeenCalledWith(
      'online',
      expect.any(Function),
    );
    expect(removeSpy).toHaveBeenCalledWith(
      'offline',
      expect.any(Function),
    );

    addSpy.mockRestore();
    removeSpy.mockRestore();
  });
});
