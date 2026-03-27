import { useCallback, useRef, useState } from 'react';
import { useKeyboardShortcut } from '@/hooks/use-keyboard';
import { AssetViewer } from '@/components/asset/asset-viewer';
import { TranscriptPanel } from './transcript-panel';
import { SceneBrowser } from './scene-browser';
import { SearchBar } from './search-bar';
import type { Asset } from '@/types/asset';
import type {
  TranscriptSegment,
  SceneInfo,
  SearchResult,
} from '@/types/transcript';

interface ReviewWorkspaceProps {
  caseId: string;
  asset: Asset;
  assetSrc: string;
  segments: TranscriptSegment[];
  scenes: SceneInfo[];
  onCreateAnnotation?: (text: string) => void;
  onSearchResultClick?: (result: SearchResult) => void;
  rightPanel?: React.ReactNode;
}

type FocusedPanel = 'video' | 'transcript' | 'right';

const panelOrder: FocusedPanel[] = ['video', 'transcript', 'right'];

export function ReviewWorkspace(
  props: ReviewWorkspaceProps,
): React.ReactElement {
  const {
    caseId,
    asset,
    assetSrc,
    segments,
    scenes,
    onCreateAnnotation,
    onSearchResultClick,
    rightPanel,
  } = props;

  const [currentTime, setCurrentTime] = useState(0);
  const [focusedPanel, setFocusedPanel] = useState<FocusedPanel>('video');
  const videoRef = useRef<HTMLDivElement>(null);

  // seek video to a specific time
  const handleSeek = useCallback((time: number) => {
    const v = document.querySelector(
      '[data-testid="video-element"]',
    ) as HTMLVideoElement | null;
    if (v) {
      v.currentTime = time;
      setCurrentTime(time);
    }
  }, []);

  // track video time updates
  const handleTimeUpdate = useCallback(() => {
    const v = document.querySelector(
      '[data-testid="video-element"]',
    ) as HTMLVideoElement | null;
    if (v) {
      setCurrentTime(v.currentTime);
    }
  }, []);

  // install timeupdate listener on mount
  // (uses interval since asset-viewer owns the element)
  useState(() => {
    const interval = setInterval(handleTimeUpdate, 250);
    return () => clearInterval(interval);
  });

  // keyboard: tab cycles panels
  useKeyboardShortcut(
    'tab',
    () => {
      const idx = panelOrder.indexOf(focusedPanel);
      const next = panelOrder[(idx + 1) % panelOrder.length];
      setFocusedPanel(next);
    },
    [focusedPanel],
  );

  // keyboard: n/p for next/prev segment
  useKeyboardShortcut(
    'n',
    () => {
      const next = segments.find((s) => s.startTime > currentTime);
      if (next) handleSeek(next.startTime);
    },
    [segments, currentTime, handleSeek],
  );

  useKeyboardShortcut(
    'p',
    () => {
      // find last segment before current time
      for (let i = segments.length - 1; i >= 0; i--) {
        if (segments[i].startTime < currentTime - 0.5) {
          handleSeek(segments[i].startTime);
          return;
        }
      }
    },
    [segments, currentTime, handleSeek],
  );

  return (
    <div data-testid="review-workspace" className="flex h-full flex-col">
      {/* top search bar */}
      <div className="border-b border-border px-4 py-2">
        <SearchBar caseId={caseId} onResultClick={onSearchResultClick} />
      </div>

      {/* main content grid */}
      <div
        className="grid flex-1 overflow-hidden"
        style={{
          gridTemplateColumns: '1fr 1fr 320px',
          gridTemplateRows: '1fr auto',
        }}
      >
        {/* left: video + scene browser */}
        <section
          aria-label="Video player"
          data-testid="panel-video"
          className={`flex flex-col overflow-hidden border-r border-border ${
            focusedPanel === 'video' ? 'ring-2 ring-inset ring-primary/30' : ''
          }`}
        >
          <div className="flex-1 overflow-y-auto p-3" ref={videoRef}>
            <AssetViewer asset={asset} src={assetSrc} />
          </div>
        </section>

        {/* center: transcript */}
        <section
          aria-label="Transcript"
          data-testid="panel-transcript"
          className={`flex flex-col overflow-hidden border-r border-border ${
            focusedPanel === 'transcript'
              ? 'ring-2 ring-inset ring-primary/30'
              : ''
          }`}
        >
          <TranscriptPanel
            segments={segments}
            currentTime={currentTime}
            onSeek={handleSeek}
            onCreateAnnotation={onCreateAnnotation}
          />
        </section>

        {/* right: annotations / ocr (tabbed) */}
        <section
          aria-label="Annotations"
          data-testid="panel-right"
          className={`flex flex-col overflow-hidden ${
            focusedPanel === 'right' ? 'ring-2 ring-inset ring-primary/30' : ''
          }`}
        >
          {rightPanel ?? (
            <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
              Annotations panel
            </div>
          )}
        </section>

        {/* bottom: scene browser spanning full width */}
        <div
          className="col-span-3 border-t border-border"
          data-testid="scene-strip"
        >
          <SceneBrowser
            scenes={scenes}
            currentTime={currentTime}
            onSeek={handleSeek}
            compact
          />
        </div>
      </div>
    </div>
  );
}
