import { useCallback, useEffect, useRef, useState } from 'react';
import { useCapabilities } from '@/hooks/use-capabilities';
import { useKeyboardShortcut } from '@/hooks/use-keyboard';
import { useWaveform } from '@/hooks/use-waveform';
import { loadPdf, type LoadedPdf } from '@/lib/pdf';
import type { Asset } from '@/types/asset';

// waveform bar colors — played vs remaining
const WAVE_PLAYED = 'hsl(221.2, 83.2%, 53.3%)';
const WAVE_REMAINING = 'hsl(215.4, 16.3%, 46.9%)';

interface AssetViewerProps {
  asset: Asset;
  src: string;
  // exposes the underlying <video> element so hosts (the review
  // workspace) can seek without querying the dom
  videoRef?: React.MutableRefObject<HTMLVideoElement | null>;
  onTimeUpdate?: (time: number) => void;
}

// frame numbers are only shown when the extracted metadata carries a
// real frame rate; estimating one would mislabel evidence frames
function assetFrameRate(asset: Asset): number | null {
  const meta = asset.metadataExtracted;
  if (!meta || typeof meta !== 'object') return null;
  const fps = (meta as Record<string, unknown>).frameRate;
  return typeof fps === 'number' && fps > 0 ? fps : null;
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

function VideoViewer(props: {
  src: string;
  filename: string;
  fps?: number | null;
  externalRef?: React.MutableRefObject<HTMLVideoElement | null>;
  onTimeUpdate?: (time: number) => void;
}): React.ReactElement {
  const { src, filename, fps = null, externalRef, onTimeUpdate } = props;
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [inPoint, setInPoint] = useState<number | null>(null);
  const [outPoint, setOutPoint] = useState<number | null>(null);
  // some webviews (notably WebKitGTK on linux) lack the codecs to decode
  // common formats; surface a download instead of a silent black frame.
  const [failed, setFailed] = useState(false);

  const frameNumber = fps ? Math.floor(currentTime * fps) : null;

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

    const onTime = (): void => {
      setCurrentTime(v.currentTime);
      onTimeUpdate?.(v.currentTime);
    };
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
  }, [onTimeUpdate]);

  if (failed) {
    return (
      <DownloadFallback
        src={src}
        filename={filename}
        message="This video can’t play in this app — download it to view"
      />
    );
  }

  return (
    <div data-testid="video-viewer">
      <video
        ref={(el) => {
          videoRef.current = el;
          if (externalRef) {
            externalRef.current = el;
          }
        }}
        src={src}
        className="w-full rounded"
        data-testid="video-element"
        aria-label={`Video: ${filename}`}
        onError={() => setFailed(true)}
      >
        <track kind="captions" />
      </video>

      {/* timestamp display */}
      <div
        className="text-foreground mt-2 flex items-center gap-4 font-mono text-sm"
        data-testid="timestamp-display"
      >
        <span>{formatTime(currentTime)}</span>
        <span className="text-muted-foreground">/</span>
        <span>{formatTime(duration)}</span>
        {frameNumber !== null && (
          <span className="text-muted-foreground text-xs">
            Frame {frameNumber}
          </span>
        )}
      </div>

      {/* controls */}
      <div className="mt-2 flex items-center gap-2">
        <button
          type="button"
          onClick={togglePlay}
          data-testid="play-pause"
          className="bg-primary text-primary-foreground rounded px-3 py-1 text-xs font-medium"
        >
          {playing ? 'Pause' : 'Play'}
        </button>

        {inPoint !== null && (
          <span className="text-muted-foreground text-xs">
            In: {formatTime(inPoint)}
          </span>
        )}
        {outPoint !== null && (
          <span className="text-muted-foreground text-xs">
            Out: {formatTime(outPoint)}
          </span>
        )}
      </div>
    </div>
  );
}

function drawWaveform(
  canvas: HTMLCanvasElement,
  peaks: number[],
  progress: number,
): void {
  const ctx = canvas.getContext('2d');
  if (!ctx) return;
  const w = canvas.width;
  const h = canvas.height;
  const count = peaks.length;
  const barWidth = w / count;

  ctx.clearRect(0, 0, w, h);
  for (let i = 0; i < count; i++) {
    const barHeight = Math.max(1, peaks[i] * h * 0.9);
    const x = i * barWidth;
    const y = (h - barHeight) / 2;
    ctx.fillStyle = i / count < progress ? WAVE_PLAYED : WAVE_REMAINING;
    ctx.fillRect(x, y, Math.max(1, barWidth), barHeight);
  }
}

function WaveformUnavailable(props: { remedy?: string }): React.ReactElement {
  return (
    <div
      data-testid="waveform-unavailable"
      className="bg-muted text-muted-foreground flex h-24 w-full flex-col items-center justify-center rounded px-4 text-center text-sm"
    >
      <p>Waveform unavailable</p>
      {props.remedy && <p className="mt-1 text-xs">{props.remedy}</p>}
    </div>
  );
}

// renders the real amplitude peaks decoded from the audio at ingest.
// there is deliberately no synthesized fallback: when peaks are absent
// the reviewer sees an honest "unavailable" state, never a fake shape.
function AudioWaveform(props: {
  caseId: string;
  assetId: string;
  audioRef: React.RefObject<HTMLAudioElement | null>;
  currentTime: number;
  duration: number;
}): React.ReactElement {
  const { caseId, assetId, audioRef, currentTime, duration } = props;
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const { data, isLoading } = useWaveform(caseId, assetId);
  const capabilities = useCapabilities();
  const peaks = data?.peaks ?? null;

  // redraw whenever the peaks arrive or playback advances
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !peaks || peaks.length === 0) return;
    const progress = duration > 0 ? currentTime / duration : 0;
    drawWaveform(canvas, peaks, progress);
  }, [peaks, currentTime, duration]);

  const handleClick = (e: React.MouseEvent): void => {
    const canvas = canvasRef.current;
    const audio = audioRef.current;
    if (!canvas || !audio || !duration) return;
    const rect = canvas.getBoundingClientRect();
    const ratio = (e.clientX - rect.left) / rect.width;
    audio.currentTime = ratio * duration;
  };

  if (isLoading) {
    return (
      <div
        data-testid="waveform-loading"
        className="bg-muted text-muted-foreground flex h-24 w-full items-center justify-center rounded text-sm"
      >
        Loading waveform…
      </div>
    );
  }

  if (!peaks || peaks.length === 0) {
    // surface the fix only when the decoder itself is the reason
    const media = capabilities.data?.engines.mediaPipeline;
    const remedy = media?.status === 'missing' ? (media.remedy ?? '') : '';
    return <WaveformUnavailable remedy={remedy || undefined} />;
  }

  return (
    <canvas
      ref={canvasRef}
      width={640}
      height={96}
      data-testid="audio-waveform"
      className="bg-muted h-24 w-full cursor-pointer rounded"
      onClick={handleClick}
    />
  );
}

function AudioViewer(props: {
  src: string;
  filename: string;
  caseId: string;
  assetId: string;
}): React.ReactElement {
  const { src, filename, caseId, assetId } = props;
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
      <audio ref={audioRef} src={src} aria-label={`Audio: ${filename}`} />

      <AudioWaveform
        caseId={caseId}
        assetId={assetId}
        audioRef={audioRef}
        currentTime={currentTime}
        duration={duration}
      />

      <div
        className="text-foreground mt-2 font-mono text-sm"
        data-testid="timestamp-display"
      >
        {formatTime(currentTime)} / {formatTime(duration)}
      </div>

      <button
        type="button"
        onClick={togglePlay}
        data-testid="play-pause"
        className={
          'bg-primary mt-2 rounded px-3 py-1 text-xs ' +
          'text-primary-foreground font-medium'
        }
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
      <div className="border-border overflow-auto rounded border">
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
          className="bg-muted text-foreground rounded px-2 py-1 text-xs"
        >
          -
        </button>
        <span className="text-muted-foreground text-xs">
          {Math.round(zoom * 100)}%
        </span>
        <button
          type="button"
          onClick={zoomIn}
          aria-label="Zoom in"
          className="bg-muted text-foreground rounded px-2 py-1 text-xs"
        >
          +
        </button>
        <button
          type="button"
          onClick={resetZoom}
          className="bg-muted text-foreground rounded px-2 py-1 text-xs"
        >
          Reset
        </button>
      </div>
    </div>
  );
}

function DownloadFallback(props: {
  src: string;
  filename: string;
  message: string;
}): React.ReactElement {
  return (
    <div className="border-border bg-muted flex h-48 flex-col items-center justify-center rounded border">
      <p className="text-muted-foreground text-sm">{props.message}</p>
      <a
        href={props.src}
        download={props.filename}
        className="text-primary mt-2 text-sm font-medium hover:underline"
      >
        Download file
      </a>
    </div>
  );
}

function PdfViewer(props: {
  src: string;
  filename: string;
}): React.ReactElement {
  const { src, filename } = props;
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const pdfRef = useRef<LoadedPdf | null>(null);
  const [numPages, setNumPages] = useState(0);
  const [page, setPage] = useState(1);
  const [scale, setScale] = useState(1.2);
  const [status, setStatus] = useState<'loading' | 'ready' | 'error'>(
    'loading',
  );

  // load (and tear down) the document. the parent keys this component by
  // src, so a new src remounts with fresh state — no synchronous reset.
  useEffect(() => {
    let cancelled = false;
    loadPdf(src)
      .then((pdf) => {
        if (cancelled) {
          pdf.destroy();
          return;
        }
        pdfRef.current = pdf;
        setNumPages(pdf.numPages);
        setStatus('ready');
      })
      .catch(() => {
        if (!cancelled) setStatus('error');
      });
    return () => {
      cancelled = true;
      pdfRef.current?.destroy();
      pdfRef.current = null;
    };
  }, [src]);

  // (re)render the current page on page/zoom change once loaded.
  useEffect(() => {
    const pdf = pdfRef.current;
    const canvas = canvasRef.current;
    if (status !== 'ready' || !pdf || !canvas) return;
    let cancelled = false;
    pdf.renderPage(page, canvas, scale).catch(() => {
      if (!cancelled) setStatus('error');
    });
    return () => {
      cancelled = true;
    };
  }, [status, page, scale]);

  const prev = useCallback(() => setPage((p) => Math.max(1, p - 1)), []);
  const next = useCallback(
    () => setPage((p) => Math.min(numPages, p + 1)),
    [numPages],
  );
  const zoomOut = useCallback(
    () => setScale((s) => Math.max(0.5, s - 0.25)),
    [],
  );
  const zoomIn = useCallback(() => setScale((s) => Math.min(3, s + 0.25)), []);

  if (status === 'error') {
    return (
      <DownloadFallback
        src={src}
        filename={filename}
        message="Couldn’t render this PDF — download it to view"
      />
    );
  }

  return (
    <div data-testid="document-viewer">
      <div
        data-testid="pdf-viewer"
        className="border-border bg-muted max-h-[600px] overflow-auto rounded border"
      >
        <canvas
          ref={canvasRef}
          data-testid="pdf-canvas"
          aria-label={`PDF: ${filename}`}
          className="mx-auto block"
        />
      </div>
      {status === 'loading' && (
        <p className="text-muted-foreground mt-2 text-sm">Loading PDF…</p>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={prev}
          disabled={page <= 1}
          className="bg-muted text-foreground rounded px-2 py-1 text-xs disabled:opacity-50"
        >
          Prev
        </button>
        <span className="text-muted-foreground text-xs">
          Page {page} / {numPages || '…'}
        </span>
        <button
          type="button"
          onClick={next}
          disabled={numPages === 0 || page >= numPages}
          className="bg-muted text-foreground rounded px-2 py-1 text-xs disabled:opacity-50"
        >
          Next
        </button>
        <span className="text-muted-foreground mx-2">|</span>
        <button
          type="button"
          onClick={zoomOut}
          aria-label="Zoom out"
          className="bg-muted text-foreground rounded px-2 py-1 text-xs"
        >
          -
        </button>
        <span className="text-muted-foreground text-xs">
          {Math.round(scale * 100)}%
        </span>
        <button
          type="button"
          onClick={zoomIn}
          aria-label="Zoom in"
          className="bg-muted text-foreground rounded px-2 py-1 text-xs"
        >
          +
        </button>
        <a
          href={src}
          download={filename}
          className="text-primary ml-2 text-xs font-medium hover:underline"
        >
          Download
        </a>
      </div>
    </div>
  );
}

function DocumentViewer(props: {
  src: string;
  filename: string;
  mimeType: string;
}): React.ReactElement {
  const { src, filename, mimeType } = props;

  // render pdfs ourselves with pdf.js — the webview's native viewer is
  // unavailable on some platforms (e.g. WebKitGTK). other document types
  // are download-only.
  if (mimeType === 'application/pdf') {
    return <PdfViewer key={src} src={src} filename={filename} />;
  }

  return (
    <div data-testid="document-viewer">
      <DownloadFallback
        src={src}
        filename={filename}
        message="Preview not available"
      />
    </div>
  );
}

export function AssetViewer(props: AssetViewerProps): React.ReactElement {
  const { asset, src, videoRef, onTimeUpdate } = props;

  switch (asset.mediaType) {
    case 'video':
      return (
        <VideoViewer
          src={src}
          filename={asset.originalFilename}
          fps={assetFrameRate(asset)}
          externalRef={videoRef}
          onTimeUpdate={onTimeUpdate}
        />
      );
    case 'audio':
      return (
        <AudioViewer
          src={src}
          filename={asset.originalFilename}
          caseId={asset.caseId}
          assetId={asset.id}
        />
      );
    case 'image':
      return <ImageViewer src={src} alt={asset.originalFilename} />;
    case 'document':
    case 'other':
      return (
        <DocumentViewer
          src={src}
          filename={asset.originalFilename}
          mimeType={asset.mimeType}
        />
      );
  }
}
