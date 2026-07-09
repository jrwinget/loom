import { renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useToast } from '@/hooks/use-toast';

const addToast = vi.fn(() => 'toast-id');
const removeToast = vi.fn();

vi.mock('@/stores/toast-store', () => ({
  useToastStore: (selector: (s: unknown) => unknown) =>
    selector({ addToast, removeToast }),
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe('useToast', () => {
  it('dispatches a success toast for toast.success', () => {
    const { result } = renderHook(() => useToast());
    result.current.toast.success('saved');

    expect(addToast).toHaveBeenCalledWith({
      type: 'success',
      message: 'saved',
    });
  });

  it('dispatches an error toast for toast.error', () => {
    const { result } = renderHook(() => useToast());
    result.current.toast.error('boom');

    expect(addToast).toHaveBeenCalledWith({ type: 'error', message: 'boom' });
  });

  it('dispatches an info toast for toast.info', () => {
    const { result } = renderHook(() => useToast());
    result.current.toast.info('heads up');

    expect(addToast).toHaveBeenCalledWith({
      type: 'info',
      message: 'heads up',
    });
  });

  it('dispatches a warning toast for toast.warning', () => {
    const { result } = renderHook(() => useToast());
    result.current.toast.warning('careful');

    expect(addToast).toHaveBeenCalledWith({
      type: 'warning',
      message: 'careful',
    });
  });

  it('removes the toast by id for toast.dismiss', () => {
    const { result } = renderHook(() => useToast());
    result.current.toast.dismiss('toast-9');

    expect(removeToast).toHaveBeenCalledWith('toast-9');
  });
});
