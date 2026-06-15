import { useCallback, useEffect, useRef, useState } from 'react';

interface VideoAsset {
  id: string;
  src: string;
  label: string;
  captureTime: string;
}

interface MultiVideoSyncProps {
  assets: VideoAsset[];
}

export function MultiVideoSync(props: MultiVideoSyncProps): React.ReactElement {
  const { assets } = props;
  const videoRefs = useRef<(HTMLVideoElement | null)[]>([]);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);

  // master is the first video
  const masterCaptureMs =
    assets.length > 0 ? new Date(assets[0].captureTime).getTime() : 0;

  const handleTimeUpdate = useCallback(() => {
    const master = videoRefs.current[0];
    if (!master) return;

    const masterTime = master.currentTime;
    setCurrentTime(masterTime);

    // sync other videos based on capture time offset
    for (let i = 1; i < videoRefs.current.length; i++) {
      const video = videoRefs.current[i];
      if (!video) continue;

      const otherCaptureMs = new Date(assets[i].captureTime).getTime();
      const offsetSec = (otherCaptureMs - masterCaptureMs) / 1000;
      const targetTime = masterTime + offsetSec;

      // only seek if difference is significant
      if (Math.abs(video.currentTime - targetTime) > 0.3) {
        video.currentTime = Math.max(0, targetTime);
      }
    }
  }, [assets, masterCaptureMs]);

  const handlePlayPause = useCallback(() => {
    const allVideos = videoRefs.current.filter(Boolean);
    if (playing) {
      allVideos.forEach((v) => v?.pause());
    } else {
      allVideos.forEach((v) => {
        void v?.play();
      });
    }
    setPlaying(!playing);
  }, [playing]);

  const handleSeek = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const time = Number(e.target.value);
    const master = videoRefs.current[0];
    if (master) {
      master.currentTime = time;
    }
  }, []);

  // cleanup: pause on unmount
  useEffect(() => {
    const refs = videoRefs.current;
    return () => {
      refs.forEach((v) => v?.pause());
    };
  }, []);

  if (assets.length === 0) {
    return (
      <div
        data-testid="multi-video-empty"
        className="flex h-48 items-center justify-center"
      >
        <p className="text-sm text-muted-foreground">No videos to sync</p>
      </div>
    );
  }

  // limit to 4 videos
  const visibleAssets = assets.slice(0, 4);

  return (
    <div data-testid="multi-video-sync" className="space-y-3">
      {/* video grid */}
      <div
        className={`grid gap-2 ${
          visibleAssets.length <= 2 ? 'grid-cols-2' : 'grid-cols-2 grid-rows-2'
        }`}
      >
        {visibleAssets.map((asset, i) => {
          const offsetSec =
            i === 0
              ? 0
              : (new Date(asset.captureTime).getTime() - masterCaptureMs) /
                1000;

          return (
            <div key={asset.id} className="relative">
              <video
                ref={(el) => {
                  videoRefs.current[i] = el;
                }}
                src={asset.src}
                onTimeUpdate={i === 0 ? handleTimeUpdate : undefined}
                onLoadedMetadata={
                  i === 0
                    ? (e) => setDuration(e.currentTarget.duration)
                    : undefined
                }
                className="h-full w-full rounded bg-black"
                data-testid={`video-${asset.id}`}
                muted
                playsInline
              />
              <div className="absolute bottom-1 left-1 rounded bg-black/60 px-1.5 py-0.5 text-xs text-white">
                {asset.label}
                {i > 0 && (
                  <span className="ml-1 text-yellow-300">
                    ({offsetSec >= 0 ? '+' : ''}
                    {offsetSec.toFixed(1)}s)
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* shared controls */}
      <div className="flex items-center gap-3 px-2">
        <button
          type="button"
          data-testid="play-pause-btn"
          onClick={handlePlayPause}
          className="rounded bg-primary px-3 py-1.5 text-sm text-primary-foreground"
        >
          {playing ? 'Pause' : 'Play'}
        </button>
        <input
          type="range"
          min={0}
          max={duration || 100}
          value={currentTime}
          onChange={handleSeek}
          data-testid="seek-slider"
          className="flex-1"
          aria-label="Seek"
        />
        <span className="text-xs text-muted-foreground">
          {currentTime.toFixed(1)}s
        </span>
      </div>
    </div>
  );
}
