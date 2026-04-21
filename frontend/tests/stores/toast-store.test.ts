import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useToastStore } from '@/stores/toast-store';

describe('toast-store', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // reset store between tests
    useToastStore.setState({ toasts: [] });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('adds a toast', () => {
    const id = useToastStore.getState().addToast({
      type: 'success',
      message: 'It worked',
    });

    const toasts = useToastStore.getState().toasts;
    expect(toasts).toHaveLength(1);
    expect(toasts[0]).toMatchObject({
      id,
      type: 'success',
      message: 'It worked',
    });
  });

  it('removes a toast by id', () => {
    const id = useToastStore.getState().addToast({
      type: 'info',
      message: 'Hello',
    });

    expect(useToastStore.getState().toasts).toHaveLength(1);

    useToastStore.getState().removeToast(id);
    expect(useToastStore.getState().toasts).toHaveLength(0);
  });

  it('auto-dismisses success toasts after 5000ms', () => {
    useToastStore.getState().addToast({
      type: 'success',
      message: 'Done',
    });

    expect(useToastStore.getState().toasts).toHaveLength(1);

    vi.advanceTimersByTime(4999);
    expect(useToastStore.getState().toasts).toHaveLength(1);

    vi.advanceTimersByTime(1);
    expect(useToastStore.getState().toasts).toHaveLength(0);
  });

  it('auto-dismisses info toasts after 5000ms', () => {
    useToastStore.getState().addToast({
      type: 'info',
      message: 'FYI',
    });

    vi.advanceTimersByTime(5000);
    expect(useToastStore.getState().toasts).toHaveLength(0);
  });

  it('auto-dismisses error toasts after 8000ms', () => {
    useToastStore.getState().addToast({
      type: 'error',
      message: 'Oops',
    });

    vi.advanceTimersByTime(7999);
    expect(useToastStore.getState().toasts).toHaveLength(1);

    vi.advanceTimersByTime(1);
    expect(useToastStore.getState().toasts).toHaveLength(0);
  });

  it('auto-dismisses warning toasts after 8000ms', () => {
    useToastStore.getState().addToast({
      type: 'warning',
      message: 'Watch out',
    });

    vi.advanceTimersByTime(8000);
    expect(useToastStore.getState().toasts).toHaveLength(0);
  });

  it('uses custom duration when provided', () => {
    useToastStore.getState().addToast({
      type: 'success',
      message: 'Quick',
      duration: 1000,
    });

    vi.advanceTimersByTime(999);
    expect(useToastStore.getState().toasts).toHaveLength(1);

    vi.advanceTimersByTime(1);
    expect(useToastStore.getState().toasts).toHaveLength(0);
  });

  it('supports multiple concurrent toasts', () => {
    useToastStore.getState().addToast({
      type: 'success',
      message: 'First',
    });
    useToastStore.getState().addToast({
      type: 'error',
      message: 'Second',
    });

    expect(useToastStore.getState().toasts).toHaveLength(2);

    // first one (success) dismisses at 5s
    vi.advanceTimersByTime(5000);
    expect(useToastStore.getState().toasts).toHaveLength(1);
    expect(
      useToastStore.getState().toasts[0]?.message,
    ).toBe('Second');

    // second one (error) dismisses at 8s
    vi.advanceTimersByTime(3000);
    expect(useToastStore.getState().toasts).toHaveLength(0);
  });

  it('returns the toast id from addToast', () => {
    const id = useToastStore.getState().addToast({
      type: 'info',
      message: 'Test',
    });

    expect(typeof id).toBe('string');
    expect(id.length).toBeGreaterThan(0);
  });
});
