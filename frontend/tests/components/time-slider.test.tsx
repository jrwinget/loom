/// <reference types="@testing-library/jest-dom" />
import { fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { TimeSlider } from '@/components/map/time-slider';

const MIN = '2026-01-01T00:00:00.000Z';
const MAX = '2026-01-31T00:00:00.000Z';
const START = '2026-01-10T00:00:00.000Z';
const END = '2026-01-20T00:00:00.000Z';

function ts(iso: string): string {
  return String(new Date(iso).getTime());
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe('TimeSlider', () => {
  it('clamps the start handle so it cannot move past the end', () => {
    const onChange = vi.fn();
    render(
      <TimeSlider
        min={MIN}
        max={MAX}
        startValue={START}
        endValue={END}
        onChange={onChange}
      />,
    );

    fireEvent.change(screen.getByTestId('slider-start'), {
      target: { value: ts('2026-01-25T00:00:00.000Z') },
    });
    vi.advanceTimersByTime(300);

    expect(onChange).toHaveBeenCalledWith(END, END);
  });

  it('clamps the end handle so it cannot move before the start', () => {
    const onChange = vi.fn();
    render(
      <TimeSlider
        min={MIN}
        max={MAX}
        startValue={START}
        endValue={END}
        onChange={onChange}
      />,
    );

    fireEvent.change(screen.getByTestId('slider-end'), {
      target: { value: ts('2026-01-05T00:00:00.000Z') },
    });
    vi.advanceTimersByTime(300);

    expect(onChange).toHaveBeenCalledWith(START, START);
  });

  it('debounces the change emission until the delay elapses', () => {
    const onChange = vi.fn();
    render(
      <TimeSlider
        min={MIN}
        max={MAX}
        startValue={START}
        endValue={END}
        onChange={onChange}
      />,
    );

    fireEvent.change(screen.getByTestId('slider-end'), {
      target: { value: ts('2026-01-15T00:00:00.000Z') },
    });

    expect(onChange).not.toHaveBeenCalled();
    vi.advanceTimersByTime(300);
    expect(onChange).toHaveBeenCalledWith(START, '2026-01-15T00:00:00.000Z');
  });

  it('resets the handles when the controlling range props change', () => {
    const onChange = vi.fn();
    const { rerender } = render(
      <TimeSlider
        min={MIN}
        max={MAX}
        startValue={START}
        endValue={END}
        onChange={onChange}
      />,
    );

    rerender(
      <TimeSlider
        min={MIN}
        max={MAX}
        startValue={START}
        endValue={'2026-01-28T00:00:00.000Z'}
        onChange={onChange}
      />,
    );

    expect(screen.getByTestId('slider-end')).toHaveValue(
      ts('2026-01-28T00:00:00.000Z'),
    );
  });
});
