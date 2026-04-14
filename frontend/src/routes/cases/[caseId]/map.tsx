import { useCallback, useState } from 'react';
import { useParams } from 'react-router-dom';
import { CaseMap } from '@/components/map/case-map';
import { TimeSlider } from '@/components/map/time-slider';
import { useGeoBounds } from '@/hooks/use-geo';

export function MapPage(): React.ReactElement {
  const { caseId } = useParams<{ caseId: string }>();
  const safeId = caseId ?? '';

  const { data: bounds } = useGeoBounds(safeId);

  const defaultStart = bounds?.timeStart ?? new Date(0).toISOString();
  const defaultEnd = bounds?.timeEnd ?? new Date().toISOString();

  const [timeStart, setTimeStart] = useState<string | undefined>();
  const [timeEnd, setTimeEnd] = useState<string | undefined>();

  const handleTimeChange = useCallback((start: string, end: string) => {
    setTimeStart(start);
    setTimeEnd(end);
  }, []);

  return (
    <div className="flex h-full flex-col">
      {/* map area: 70% height */}
      <div className="flex-[7] overflow-hidden p-4">
        <CaseMap caseId={safeId} timeStart={timeStart} timeEnd={timeEnd} />
      </div>

      {/* time slider: bottom */}
      <div className="border-t border-border">
        <TimeSlider
          min={defaultStart}
          max={defaultEnd}
          startValue={timeStart ?? defaultStart}
          endValue={timeEnd ?? defaultEnd}
          onChange={handleTimeChange}
        />
      </div>
    </div>
  );
}
