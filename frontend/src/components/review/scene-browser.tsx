import { useMemo, useRef, useEffect } from 'react';
import type { SceneInfo } from '@/types/transcript';
import { WhyPopover } from './why-popover';

interface SceneBrowserProps {
  scenes: SceneInfo[];
  currentTime: number;
  onSeek: (time: number) => void;
  compact?: boolean;
}

function formatTimestamp(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${String(m).padStart(2, '0')}:` + `${String(s).padStart(2, '0')}`;
}

export function SceneBrowser(props: SceneBrowserProps): React.ReactElement {
  const { scenes, currentTime, onSeek, compact = false } = props;

  const activeRef = useRef<HTMLButtonElement>(null);

  // find current scene
  const activeSceneId = useMemo(() => {
    for (let i = scenes.length - 1; i >= 0; i--) {
      if (
        currentTime >= scenes[i].startTime &&
        currentTime < scenes[i].endTime
      ) {
        return scenes[i].id;
      }
    }
    return null;
  }, [scenes, currentTime]);

  // scroll active scene into view
  useEffect(() => {
    if (
      activeRef.current &&
      typeof activeRef.current.scrollIntoView === 'function'
    ) {
      activeRef.current.scrollIntoView({
        behavior: 'smooth',
        block: 'nearest',
        inline: 'nearest',
      });
    }
  }, [activeSceneId]);

  if (scenes.length === 0) {
    return (
      <div
        data-testid="scene-browser"
        className="flex h-16 items-center justify-center text-xs text-muted-foreground"
      >
        No scenes detected
      </div>
    );
  }

  return (
    <div data-testid="scene-browser" className="flex flex-col gap-1">
      <div className="flex items-center gap-2 px-2">
        <span className="text-[10px] font-medium text-muted-foreground">
          Scenes
        </span>
        <span
          data-testid="ai-generated-badge"
          aria-label="AI-generated content"
          className="rounded bg-amber-100 px-1.5 py-0 text-[10px] font-medium text-amber-900 dark:bg-amber-950 dark:text-amber-200"
        >
          AI-generated
        </span>
      </div>
      <div className="flex gap-2 overflow-x-auto px-2 py-2">
        {scenes.map((scene) => {
          const isActive = scene.id === activeSceneId;
          return (
            <div key={scene.id} className="relative flex-shrink-0">
              <button
                ref={isActive ? activeRef : undefined}
                type="button"
                data-testid={`scene-${scene.id}`}
                data-active={isActive}
                onClick={() => onSeek(scene.startTime)}
                aria-label={`Scene ${scene.sceneNumber}: ${formatTimestamp(scene.startTime)} to ${formatTimestamp(scene.endTime)}`}
                aria-current={isActive ? 'true' : undefined}
                title={
                  `Scene ${scene.sceneNumber}: ` +
                  `${formatTimestamp(scene.startTime)} - ` +
                  `${formatTimestamp(scene.endTime)}`
                }
                className={`rounded border transition-colors ${
                  isActive
                    ? 'border-primary ring-2 ring-primary/50'
                    : 'border-border hover:border-primary/50'
                }`}
              >
                {/* thumbnail or placeholder */}
                <div className="flex h-12 w-20 items-center justify-center rounded-t bg-muted text-xs text-muted-foreground">
                  {scene.thumbnailUrl ? (
                    <img
                      src={scene.thumbnailUrl}
                      alt={`Scene ${scene.sceneNumber}`}
                      className="h-full w-full rounded-t object-cover"
                    />
                  ) : (
                    <span>S{scene.sceneNumber}</span>
                  )}
                </div>
                {!compact && (
                  <div className="px-1 py-0.5 text-center text-[10px] text-muted-foreground">
                    {formatTimestamp(scene.startTime)}
                    <span className="mx-0.5">-</span>
                    {formatTimestamp(scene.endTime)}
                  </div>
                )}
              </button>
              <div className="absolute right-0.5 top-0.5">
                <WhyPopover
                  modelName={scene.modelName}
                  modelVersion={scene.modelVersion}
                  modelParams={scene.modelParams}
                  confidence={null}
                  scope={`Scene ${scene.sceneNumber}`}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
