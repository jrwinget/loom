import { useCallback, useEffect, useRef, useState } from 'react';
import { useKeyboardShortcut } from '@/hooks/use-keyboard';
import type { Asset } from '@/types/asset';

interface AssetViewerProps {
  asset: Asset;
  src: string;
}

function formatTime(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 1000);
  if (h > 0) {
    return (
      `${String(h).padStart(2, '0')}:` +
      `${String(m).padStart(2, '0')}:` +
      `${String(s).padStart(2, '0')}.` +
      `${String(ms).padStart(3, '0')}`
    );
  }
  return (
    `${String(m).padStart(2, '0')}:` +
    `${String(s).padStart(2, '0')}.` +
    `${String(ms).padStart(3, '0')}`
  );
}

function VideoViewer(props: { src: string }): React.ReactElement {
  const { src } = props;
  const videoRef = useRef<HTMLVideoElement>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [inPoint, setInPoint] = useState<number | null>(null);
  const [outPoint, setOutPoint] = useState<number | null>(null);

  // ~30fps frame estimate
  const frameNumber = Math.floor(currentTime * 30);

  const togglePlay = useCallback(() => {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) {
      void v.play();
      setPlaying(true);
    } else {
      v.pause();
      setPlaying(false);
    }
  }, []);

  const skip = useCallback((delta: number) => {
    const v = videoRef.current;
    if (!v) return;
    v.currentTime = Math.max(0, Math.min(v.duration, v.currentTime + delta));
  }, []);

  const markIn = useCallback(() => {
    setInPoint(currentTime);
  }, [currentTime]);

  const markOut = useCallback(() => {
    setOutPoint(currentTime);
  }, [currentTime]);

  // keyboard shortcuts
  useKeyboardShortcut('space', togglePlay, [togglePlay]);
  useKeyboardShortcut('left', () => skip(-5), [skip]);
  useKeyboardShortcut('right', () => skip(5), [skip]);
  useKeyboardShortcut('shift+left', () => skip(-1), [skip]);
  useKeyboardShortcut('shift+right', () => skip(1), [skip]);
  useKeyboardShortcut('i', markIn, [markIn]);
  useKeyboardShortcut('o', markOut, [markOut]);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;

    const onTime = (): void => setCurrentTime(v.currentTime);
    const onMeta = (): void => setDuration(v.duration);
    const onEnded = (): void => setPlaying(false);

    v.addEventListener('timeupdate', onTime);
    v.addEventListener('loadedmetadata', onMeta);
    v.addEventListener('ended', onEnded);

    return () => {
      v.removeEventListener('timeupdate', onTime);
      v.removeEventListener('loadedmetadata', onMeta);
      v.removeEventListener('ended', onEnded);
    };
  }, []);

  return (
    <div data-testid="video-viewer">
      <video
        ref={videoRef}
        src={src}
        className="w-full rounded"
        data-testid="video-element"
      />

      {/* timestamp display */}
      <div
        className="mt-2 flex items-center gap-4 font-mono text-sm text-foreground"
        data-testid="timestamp-display"
      >
        <span>{formatTime(currentTime)}</span>
        <span className="text-muted-foreground">/</span>
        <span>{formatTime(duration)}</span>
        <span className="text-xs text-muted-foreground">
          Frame {frameNumber}
        </span>
      </div>

      {/* controls */}
      <div className="mt-2 flex items-center gap-2">
        <button
          type="button"
          onClick={togglePlay}
          data-testid="play-pause"
          className="rounded bg-primary px-3 py-1 text-xs font-medium text-primary-foreground"
        >
          {playing ? 'Pause' : 'Play'}
        </button>

        {inPoint !== null && (
          <span className="text-xs text-muted-foreground">
            In: {formatTime(inPoint)}
          </span>
        )}
        {outPoint !== null && (
          <span className="text-xs text-muted-foreground">
            Out: {formatTime(outPoint)}
          </span>
        )}
      </div>
    </div>
  );
}

function AudioViewer(props: { src: string }): React.ReactElement {
  const { src } = props;
  const audioRef = useRef<HTMLAudioElement>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playing, setPlaying] = useState(false);

  const togglePlay = useCallback(() => {
    const a = audioRef.current;
    if (!a) return;
    if (a.paused) {
      void a.play();
      setPlaying(true);
    } else {
      a.pause();
      setPlaying(false);
    }
  }, []);

  useKeyboardShortcut('space', togglePlay, [togglePlay]);

  useEffect(() => {
    const a = audioRef.current;
    if (!a) return;

    const onTime = (): void => setCurrentTime(a.currentTime);
    const onMeta = (): void => setDuration(a.duration);
    const onEnded = (): void => setPlaying(false);

    a.addEventListener('timeupdate', onTime);
    a.addEventListener('loadedmetadata', onMeta);
    a.addEventListener('ended', onEnded);

    return () => {
      a.removeEventListener('timeupdate', onTime);
      a.removeEventListener('loadedmetadata', onMeta);
      a.removeEventListener('ended', onEnded);
    };
  }, []);

  return (
    <div data-testid="audio-viewer">
      <audio ref={audioRef} src={src} />

      {/* waveform placeholder */}
      <div className="flex h-24 items-center justify-center rounded bg-muted text-sm text-muted-foreground">
        Audio waveform placeholder
      </div>

      {/* timestamp */}
      <div
        className="mt-2 font-mono text-sm text-foreground"
        data-testid="timestamp-display"
      >
        {formatTime(currentTime)} / {formatTime(duration)}
      </div>

      <button
        type="button"
        onClick={togglePlay}
        data-testid="play-pause"
        className="mt-2 rounded bg-primary px-3 py-1 text-xs font-medium text-primary-foreground"
      >
        {playing ? 'Pause' : 'Play'}
      </button>
    </div>
  );
}

function ImageViewer(props: { src: string; alt: string }): React.ReactElement {
  const { src, alt } = props;
  const [zoom, setZoom] = useState(1);

  const zoomIn = useCallback(() => setZoom((z) => Math.min(z + 0.25, 5)), []);
  const zoomOut = useCallback(
    () => setZoom((z) => Math.max(z - 0.25, 0.25)),
    [],
  );
  const resetZoom = useCallback(() => setZoom(1), []);

  return (
    <div data-testid="image-viewer">
      <div className="overflow-auto rounded border border-border">
        <img
          src={src}
          alt={alt}
          data-testid="image-element"
          style={{
            transform: `scale(${zoom})`,
            transformOrigin: 'top left',
          }}
        />
      </div>
      <div className="mt-2 flex items-center gap-2">
        <button
          type="button"
          onClick={zoomOut}
          aria-label="Zoom out"
          className="rounded bg-muted px-2 py-1 text-xs text-foreground"
        >
          -
        </button>
        <span className="text-xs text-muted-foreground">
          {Math.round(zoom * 100)}%
        </span>
        <button
          type="button"
          onClick={zoomIn}
          aria-label="Zoom in"
          className="rounded bg-muted px-2 py-1 text-xs text-foreground"
        >
          +
        </button>
        <button
          type="button"
          onClick={resetZoom}
          className="rounded bg-muted px-2 py-1 text-xs text-foreground"
        >
          Reset
        </button>
      </div>
    </div>
  );
}

function DocumentViewer(props: {
  src: string;
  filename: string;
}): React.ReactElement {
  return (
    <div
      data-testid="document-viewer"
      className="flex h-48 flex-col items-center justify-center rounded border border-border bg-muted"
    >
      <p className="text-sm text-muted-foreground">Preview not available</p>
      <a
        href={props.src}
        download={props.filename}
        className="mt-2 text-sm font-medium text-primary hover:underline"
      >
        Download file
      </a>
    </div>
  );
}

export function AssetViewer(props: AssetViewerProps): React.ReactElement {
  const { asset, src } = props;

  switch (asset.mediaType) {
    case 'video':
      return <VideoViewer src={src} />;
    case 'audio':
      return <AudioViewer src={src} />;
    case 'image':
      return <ImageViewer src={src} alt={asset.originalFilename} />;
    case 'document':
    case 'other':
      return <DocumentViewer src={src} filename={asset.originalFilename} />;
  }
}
