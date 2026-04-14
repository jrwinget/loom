import { useCallback, useEffect, useRef, useState } from 'react';

interface TimeSliderProps {
  min: string;
  max: string;
  startValue: string;
  endValue: string;
  onChange: (start: string, end: string) => void;
}

function toTimestamp(iso: string): number {
  return new Date(iso).getTime();
}

function toIso(ts: number): string {
  return new Date(ts).toISOString();
}

function formatLabel(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function TimeSlider(props: TimeSliderProps): React.ReactElement {
  const { min, max, startValue, endValue, onChange } = props;

  const minTs = toTimestamp(min);
  const maxTs = toTimestamp(max);

  const [localStart, setLocalStart] = useState(toTimestamp(startValue));
  const [localEnd, setLocalEnd] = useState(toTimestamp(endValue));
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // sync props -> local state
  useEffect(() => {
    setLocalStart(toTimestamp(startValue));
    setLocalEnd(toTimestamp(endValue));
  }, [startValue, endValue]);

  const emitChange = useCallback(
    (start: number, end: number) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        onChange(toIso(start), toIso(end));
      }, 300);
    },
    [onChange],
  );

  const handleStartChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const val = Number(e.target.value);
      const clamped = Math.min(val, localEnd);
      setLocalStart(clamped);
      emitChange(clamped, localEnd);
    },
    [localEnd, emitChange],
  );

  const handleEndChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const val = Number(e.target.value);
      const clamped = Math.max(val, localStart);
      setLocalEnd(clamped);
      emitChange(localStart, clamped);
    },
    [localStart, emitChange],
  );

  return (
    <div data-testid="time-slider" className="flex flex-col gap-2 px-4 py-3">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span data-testid="time-label-start">
          {formatLabel(toIso(localStart))}
        </span>
        <span data-testid="time-label-end">{formatLabel(toIso(localEnd))}</span>
      </div>
      <div className="flex items-center gap-4">
        <input
          type="range"
          min={minTs}
          max={maxTs}
          value={localStart}
          onChange={handleStartChange}
          data-testid="slider-start"
          className="flex-1"
          aria-label="Time range start"
        />
        <input
          type="range"
          min={minTs}
          max={maxTs}
          value={localEnd}
          onChange={handleEndChange}
          data-testid="slider-end"
          className="flex-1"
          aria-label="Time range end"
        />
      </div>
    </div>
  );
}
