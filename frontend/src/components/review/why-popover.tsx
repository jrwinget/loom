import { useCallback, useEffect, useRef, useState } from 'react';

import { cn } from '@/lib/utils';
import type { AiProvenance } from '@/types/transcript';

interface WhyPopoverProps extends AiProvenance {
  confidence: number | null;
  // context line shown at the top of the popover,
  // e.g. "Transcript segment 0:12 - 0:15".
  scope: string;
  /** optional action link text — e.g. "View source metadata". */
  sourceLabel?: string;
  /** href for the source link. */
  sourceHref?: string;
  /** override the trigger label; default is "Why?". */
  label?: string;
}

function formatConfidence(value: number | null): string {
  if (value == null) return 'Not reported';
  // whisper uses avg_log_prob (negative); others use 0-1 probability.
  // show raw up to 2 decimals; ui surfaces tooltip in any case.
  if (value < 0 || value > 1) return value.toFixed(2);
  return `${Math.round(value * 100)}%`;
}

export function WhyPopover(props: WhyPopoverProps): React.ReactElement {
  const {
    modelName,
    modelVersion,
    modelParams,
    confidence,
    scope,
    sourceLabel,
    sourceHref,
    label = 'Why?',
  } = props;

  const [open, setOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // close on click outside or escape
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!containerRef.current?.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const toggle = useCallback(() => setOpen((o) => !o), []);

  const displayModel = modelName ?? 'unknown';
  const displayVersion = modelVersion ?? 'unknown';

  return (
    <div ref={containerRef} className="relative inline-block">
      <button
        type="button"
        data-testid="why-popover-trigger"
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={(e) => {
          e.stopPropagation();
          toggle();
        }}
        className={cn(
          'border-border rounded border px-1.5 py-0 text-[10px] font-medium',
          'text-muted-foreground hover:border-foreground/40 hover:text-foreground',
          'focus:ring-primary focus:ring-1 focus:outline-hidden',
        )}
      >
        {label}
      </button>
      {open && (
        <div
          role="dialog"
          data-testid="why-popover-content"
          aria-label="AI output provenance"
          className={cn(
            'border-border bg-popover absolute z-50 mt-1 w-72 rounded border p-3',
            'text-popover-foreground text-xs shadow-md',
          )}
        >
          <p className="text-muted-foreground mb-2 text-[11px] font-semibold">
            {scope}
          </p>
          <dl className="space-y-1">
            <div className="flex justify-between gap-2">
              <dt className="text-muted-foreground">Model</dt>
              <dd className="text-right font-mono">{displayModel}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-muted-foreground">Version</dt>
              <dd className="text-right font-mono">{displayVersion}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-muted-foreground">Confidence</dt>
              <dd className="text-right">{formatConfidence(confidence)}</dd>
            </div>
            {modelParams &&
              Object.entries(modelParams).map(([key, value]) => (
                <div key={key} className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">{key}</dt>
                  <dd className="text-right font-mono">{String(value)}</dd>
                </div>
              ))}
          </dl>
          <p className="border-border text-muted-foreground mt-2 border-t pt-2 text-[10px]">
            AI output — verify before relying on it.{' '}
            <a
              href="https://github.com/jrwinget/loom/blob/main/docs/ai-model-cards.md"
              target="_blank"
              rel="noreferrer"
              className="hover:text-foreground underline"
            >
              Model card
            </a>
          </p>
          {sourceHref && sourceLabel && (
            <p className="mt-1 text-[10px]">
              <a
                href={sourceHref}
                className="text-primary hover:text-primary/80 underline"
              >
                {sourceLabel}
              </a>
            </p>
          )}
        </div>
      )}
    </div>
  );
}
