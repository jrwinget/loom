import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { TranscriptSegment } from '@/types/transcript';
import { WhyPopover } from './why-popover';

interface TranscriptPanelProps {
  segments: TranscriptSegment[];
  currentTime: number;
  onSeek: (time: number) => void;
  onCreateAnnotation?: (text: string) => void;
}

// deterministic color for each speaker
const speakerColors = [
  'text-blue-600 dark:text-blue-400',
  'text-green-600 dark:text-green-400',
  'text-purple-600 dark:text-purple-400',
  'text-orange-600 dark:text-orange-400',
  'text-pink-600 dark:text-pink-400',
  'text-teal-600 dark:text-teal-400',
];

function getSpeakerColor(label: string | null, speakers: string[]): string {
  if (!label) return 'text-muted-foreground';
  const idx = speakers.indexOf(label);
  return speakerColors[idx % speakerColors.length] ?? 'text-muted-foreground';
}

function formatTimestamp(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${String(m).padStart(2, '0')}:` + `${String(s).padStart(2, '0')}`;
}

export function TranscriptPanel(
  props: TranscriptPanelProps,
): React.ReactElement {
  const { segments, currentTime, onSeek, onCreateAnnotation } = props;

  const containerRef = useRef<HTMLDivElement>(null);
  const activeRef = useRef<HTMLDivElement>(null);
  const [selectedText, setSelectedText] = useState('');
  const [speakerFilter, setSpeakerFilter] = useState<string | null>(null);

  // unique speakers
  const speakers = useMemo(() => {
    const set = new Set<string>();
    for (const seg of segments) {
      if (seg.speakerLabel) set.add(seg.speakerLabel);
    }
    return Array.from(set).sort();
  }, [segments]);

  // filtered segments
  const filtered = useMemo(() => {
    if (!speakerFilter) return segments;
    return segments.filter((s) => s.speakerLabel === speakerFilter);
  }, [segments, speakerFilter]);

  // find current segment index
  const activeSegmentId = useMemo(() => {
    for (let i = filtered.length - 1; i >= 0; i--) {
      if (
        currentTime >= filtered[i].startTime &&
        currentTime < filtered[i].endTime
      ) {
        return filtered[i].id;
      }
    }
    return null;
  }, [filtered, currentTime]);

  // auto-scroll to active segment
  useEffect(() => {
    if (
      activeRef.current &&
      containerRef.current &&
      typeof activeRef.current.scrollIntoView === 'function'
    ) {
      activeRef.current.scrollIntoView({
        behavior: 'smooth',
        block: 'nearest',
      });
    }
  }, [activeSegmentId]);

  // track text selection for annotation creation
  const handleMouseUp = useCallback(() => {
    const selection = window.getSelection();
    const text = selection?.toString().trim() ?? '';
    setSelectedText(text);
  }, []);

  const handleCreateAnnotation = useCallback(() => {
    if (selectedText && onCreateAnnotation) {
      onCreateAnnotation(selectedText);
      setSelectedText('');
    }
  }, [selectedText, onCreateAnnotation]);

  return (
    <div data-testid="transcript-panel" className="flex h-full flex-col">
      {/* header with speaker filter */}
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <span className="text-xs font-medium text-foreground">Transcript</span>
        <span
          data-testid="ai-generated-badge"
          aria-label="AI-generated content"
          className="rounded bg-amber-100 px-1.5 py-0 text-[10px] font-medium text-amber-900 dark:bg-amber-950 dark:text-amber-200"
        >
          AI-generated
        </span>
        {speakers.length > 0 && (
          <select
            data-testid="speaker-filter"
            aria-label="Filter by speaker"
            value={speakerFilter ?? ''}
            onChange={(e) => setSpeakerFilter(e.target.value || null)}
            className="ml-auto rounded border border-border bg-card px-2 py-0.5 text-xs text-foreground"
          >
            <option value="">All speakers</option>
            {speakers.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* annotation creation button */}
      {selectedText && onCreateAnnotation && (
        <div className="border-b border-border px-3 py-1">
          <button
            type="button"
            data-testid="create-annotation-btn"
            onClick={handleCreateAnnotation}
            className="rounded bg-primary px-2 py-0.5 text-xs font-medium text-primary-foreground"
          >
            Create Annotation
          </button>
        </div>
      )}

      {/* segments list */}
      <div
        ref={containerRef}
        onMouseUp={handleMouseUp}
        className="flex-1 overflow-y-auto"
        data-testid="segments-container"
      >
        {filtered.length === 0 && (
          <p className="p-4 text-sm text-muted-foreground">
            No transcript segments available
          </p>
        )}
        {filtered.map((seg) => {
          const isActive = seg.id === activeSegmentId;
          return (
            <div
              key={seg.id}
              ref={isActive ? activeRef : undefined}
              data-testid={`segment-${seg.id}`}
              data-active={isActive}
              onClick={() => onSeek(seg.startTime)}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  onSeek(seg.startTime);
                }
              }}
              className={`cursor-pointer border-l-2 px-3 py-2 transition-colors hover:bg-accent/30 ${
                isActive
                  ? 'border-l-primary bg-accent/50'
                  : 'border-l-transparent'
              }`}
            >
              <div className="flex items-baseline gap-2">
                {seg.speakerLabel && (
                  <span
                    data-testid="speaker-label"
                    className={`text-xs font-semibold ${getSpeakerColor(
                      seg.speakerLabel,
                      speakers,
                    )}`}
                  >
                    {seg.speakerLabel}
                  </span>
                )}
                <span className="text-xs text-muted-foreground">
                  {formatTimestamp(seg.startTime)}
                  {' - '}
                  {formatTimestamp(seg.endTime)}
                </span>
                {seg.confidence !== null && seg.confidence < 0.7 && (
                  <span
                    data-testid="low-confidence"
                    className="text-xs text-yellow-600 dark:text-yellow-400"
                    title={`Confidence: ${Math.round(seg.confidence * 100)}%`}
                    aria-label={`Low confidence: ${Math.round(seg.confidence * 100)}%`}
                  >
                    ?
                  </span>
                )}
                <div
                  className="ml-auto"
                  onClick={(e) => e.stopPropagation()}
                  onKeyDown={(e) => e.stopPropagation()}
                  role="presentation"
                >
                  <WhyPopover
                    modelName={seg.modelName}
                    modelVersion={seg.modelVersion}
                    modelParams={seg.modelParams}
                    confidence={seg.confidence}
                    scope={
                      `Transcript ${formatTimestamp(seg.startTime)}` +
                      ` - ${formatTimestamp(seg.endTime)}`
                    }
                  />
                </div>
              </div>
              <p className="mt-0.5 text-sm text-foreground">{seg.text}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
