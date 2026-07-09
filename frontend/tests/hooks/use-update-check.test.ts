import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useUpdateCheck } from '@/hooks/use-update-check';

const checkForUpdate = vi.fn();
vi.mock('@/lib/tauri-bridge', () => ({
  checkForUpdate: () => checkForUpdate(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('useUpdateCheck', () => {
  it('reports no update before the initial delay elapses', () => {
    checkForUpdate.mockResolvedValue({ version: '2.0.0', notes: null });

    const { result } = renderHook(() => useUpdateCheck());

    expect(result.current.update).toBeNull();
    expect(checkForUpdate).not.toHaveBeenCalled();
  });

  it('surfaces an available update after the initial delay', async () => {
    const found = { version: '2.0.0', notes: 'shiny' };
    checkForUpdate.mockResolvedValue(found);

    const { result } = renderHook(() => useUpdateCheck());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });

    expect(result.current.update).toEqual(found);
  });

  it('suppresses an update once its version has been dismissed', async () => {
    checkForUpdate.mockResolvedValue({ version: '2.0.0', notes: null });

    const { result } = renderHook(() => useUpdateCheck());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    expect(result.current.update).not.toBeNull();

    act(() => {
      result.current.dismiss();
    });

    expect(result.current.update).toBeNull();
  });
});
