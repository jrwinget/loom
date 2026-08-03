import { useCallback, useRef, useState } from 'react';
import { useKeyboardShortcut } from '@/hooks/use-keyboard';
import { AssetViewer, type PlayerMarks } from '@/components/asset/asset-viewer';
import { TranscriptPanel } from './transcript-panel';
import { SceneBrowser } from './scene-browser';
import { SearchBar } from './search-bar';
import { LinkToEventDialog } from './link-to-event-dialog';
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
  // player in/out marks flow up from the viewer to prefill the
  // clip range when linking this asset to a timeline event
  const [marks, setMarks] = useState<PlayerMarks>({
    inPoint: null,
    outPoint: null,
  });
  const [linkDialogOpen, setLinkDialogOpen] = useState(false);
  // the asset viewer forwards its <video> element here so seeking
  // works without querying the dom
  const videoElementRef = useRef<HTMLVideoElement | null>(null);

  // seek video to a specific time
  const handleSeek = useCallback((time: number) => {
    const v = videoElementRef.current;
    if (v) {
      v.currentTime = time;
      setCurrentTime(time);
    }
  }, []);

  // time flows from the viewer's native timeupdate event
  const handleTimeUpdate = useCallback((time: number) => {
    setCurrentTime(time);
  }, []);

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
      <div className="border-border border-b px-4 py-2">
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
          className={`border-border flex flex-col overflow-hidden border-r ${
            focusedPanel === 'video' ? 'ring-primary/30 ring-2 ring-inset' : ''
          }`}
        >
          <div className="flex-1 overflow-y-auto p-3">
            <AssetViewer
              asset={asset}
              src={assetSrc}
              videoRef={videoElementRef}
              onTimeUpdate={handleTimeUpdate}
              onMarksChange={setMarks}
            />
            <button
              type="button"
              data-testid="link-to-event-btn"
              onClick={() => setLinkDialogOpen(true)}
              className={
                'border-border text-muted-foreground mt-2 rounded-md ' +
                'hover:bg-accent border px-3 py-1 text-xs'
              }
            >
              Link to event…
            </button>
          </div>
        </section>

        {linkDialogOpen && (
          <LinkToEventDialog
            caseId={caseId}
            assetId={asset.id}
            clipStart={marks.inPoint ?? undefined}
            clipEnd={marks.outPoint ?? undefined}
            onClose={() => setLinkDialogOpen(false)}
          />
        )}

        {/* center: transcript */}
        <section
          aria-label="Transcript"
          data-testid="panel-transcript"
          className={`border-border flex flex-col overflow-hidden border-r ${
            focusedPanel === 'transcript'
              ? 'ring-primary/30 ring-2 ring-inset'
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
            focusedPanel === 'right' ? 'ring-primary/30 ring-2 ring-inset' : ''
          }`}
        >
          {rightPanel ?? (
            <div className="text-muted-foreground flex h-full items-center justify-center text-sm">
              Annotations panel
            </div>
          )}
        </section>

        {/* bottom: scene browser spanning full width */}
        <div
          className="border-border col-span-3 border-t"
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
