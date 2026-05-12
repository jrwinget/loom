import { useCallback, useMemo, useState } from 'react';

import { cn } from '@/lib/utils';
import type {
  CorrelationCandidate,
  CorrelationCandidateMember,
  CorrelationStatus,
} from '@/types/correlation';

interface CorrelationPanelProps {
  candidates: CorrelationCandidate[];
  isLoading?: boolean;
  isScanning?: boolean;
  onScan?: () => void;
  onDecide?: (
    candidateId: string,
    decision: Exclude<CorrelationStatus, 'pending'>,
  ) => void;
}

// confidence tier thresholds — keep in sync with timeline filter defaults.
const HIGH_CONFIDENCE = 0.8;
const MEDIUM_CONFIDENCE = 0.5;

function confidenceTier(value: number): 'high' | 'medium' | 'low' {
  if (value >= HIGH_CONFIDENCE) return 'high';
  if (value >= MEDIUM_CONFIDENCE) return 'medium';
  return 'low';
}

const tierClasses: Record<'high' | 'medium' | 'low', string> = {
  high:
    'bg-green-100 text-green-800 ' + 'dark:bg-green-900 dark:text-green-200',
  medium:
    'bg-yellow-100 text-yellow-800 ' +
    'dark:bg-yellow-900 dark:text-yellow-200',
  low: 'bg-gray-100 text-gray-700 ' + 'dark:bg-gray-800 dark:text-gray-300',
};

const statusBadgeClasses: Record<CorrelationStatus, string> = {
  pending:
    'bg-yellow-100 text-yellow-800 ' +
    'dark:bg-yellow-900 dark:text-yellow-200',
  accepted:
    'bg-green-100 text-green-800 ' + 'dark:bg-green-900 dark:text-green-200',
  rejected:
    'bg-gray-100 text-gray-600 ' + 'dark:bg-gray-800 dark:text-gray-400',
};

function formatPct(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function formatOffset(seconds: number): string {
  // signed seconds relative to earliest member. Show sign so analysts can
  // tell who was first.
  const sign = seconds > 0 ? '+' : seconds < 0 ? '-' : '';
  const abs = Math.abs(seconds);
  if (abs < 60) return `${sign}${abs.toFixed(1)}s`;
  const minutes = Math.floor(abs / 60);
  const remainder = abs - minutes * 60;
  return `${sign}${minutes}m ${remainder.toFixed(0)}s`;
}

function memberOffsets(
  members: CorrelationCandidateMember[],
): Record<string, number | null> {
  // capture_time is server-formatted ISO string; if any member lacks one
  // we return null for that member so the UI can show "—".
  const captures = members.map((m) =>
    m.capture_time ? Date.parse(m.capture_time) : null,
  );
  const known = captures.filter((c): c is number => c !== null);
  if (known.length === 0) {
    return Object.fromEntries(members.map((m) => [m.id, null]));
  }
  const earliest = Math.min(...known);
  return Object.fromEntries(
    members.map((m, i) => {
      const ts = captures[i];
      return [m.id, ts === null ? null : (ts - earliest) / 1000];
    }),
  );
}

function ReasoningPopover(props: {
  candidateId: string;
  reasoning: CorrelationCandidate['reasoning'];
}): React.ReactElement {
  const { candidateId, reasoning } = props;
  const [open, setOpen] = useState(false);

  const toggle = useCallback(() => setOpen((o) => !o), []);

  return (
    <div className="relative inline-block">
      <button
        type="button"
        data-testid={`reasoning-trigger-${candidateId}`}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={(e) => {
          e.stopPropagation();
          toggle();
        }}
        onKeyDown={(e) => {
          if (e.key === 'Escape') setOpen(false);
        }}
        className={cn(
          'rounded border border-border px-1.5 py-0 text-[10px] font-medium',
          'text-muted-foreground hover:border-foreground/40 hover:text-foreground',
          'focus:outline-none focus:ring-1 focus:ring-primary',
        )}
      >
        Why?
      </button>
      {open && (
        <div
          role="dialog"
          data-testid={`reasoning-content-${candidateId}`}
          aria-label="Correlation reasoning"
          className={cn(
            'bg-popover absolute z-50 mt-1 w-72 rounded border border-border p-3',
            'text-popover-foreground text-xs shadow-md',
          )}
        >
          <p className="mb-2 text-[11px] font-semibold text-muted-foreground">
            Signal scores
          </p>
          <dl className="space-y-1">
            {Object.entries(reasoning).map(([signal, value]) => {
              const score =
                value && typeof value === 'object' && 'score' in value
                  ? (value as { score: number | null }).score
                  : null;
              return (
                <div key={signal} className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">{signal}</dt>
                  <dd className="text-right font-mono">
                    {score === null ? '—' : formatPct(score)}
                  </dd>
                </div>
              );
            })}
          </dl>
        </div>
      )}
    </div>
  );
}

function CandidateRow(props: {
  candidate: CorrelationCandidate;
  onDecide?: CorrelationPanelProps['onDecide'];
}): React.ReactElement {
  const { candidate, onDecide } = props;
  const tier = confidenceTier(candidate.confidence);
  const offsets = useMemo(() => memberOffsets(candidate.members), [candidate]);
  const isTerminal = candidate.status !== 'pending';

  return (
    <div
      data-testid={`candidate-${candidate.id}`}
      className="rounded border border-border p-3"
    >
      <div className="mb-2 flex items-center gap-2">
        <span
          data-testid="confidence-badge"
          data-tier={tier}
          className={cn(
            'rounded px-2 py-0.5 text-xs font-medium',
            tierClasses[tier],
          )}
        >
          {formatPct(candidate.confidence)} confidence
        </span>
        <span
          data-testid="status-badge"
          className={cn(
            'rounded px-2 py-0.5 text-xs font-medium',
            statusBadgeClasses[candidate.status],
          )}
        >
          {candidate.status}
        </span>
        <ReasoningPopover
          candidateId={candidate.id}
          reasoning={candidate.reasoning}
        />
      </div>
      <ul className="space-y-1 text-sm">
        {candidate.members.map((m) => {
          const offset = offsets[m.id];
          return (
            <li
              key={m.id}
              data-testid={`member-${m.id}`}
              className="flex items-center gap-2"
            >
              <span className="flex-1 truncate text-foreground">
                {m.original_filename ?? m.asset_id}
              </span>
              <span className="text-xs tabular-nums text-muted-foreground">
                {offset === null ? '—' : formatOffset(offset)}
              </span>
            </li>
          );
        })}
      </ul>
      {!isTerminal && onDecide && (
        <div className="mt-3 flex justify-end gap-2">
          <button
            type="button"
            data-testid={`reject-${candidate.id}`}
            onClick={() => onDecide(candidate.id, 'rejected')}
            className="rounded border border-border px-2 py-1 text-xs text-muted-foreground hover:bg-accent/30"
          >
            Reject
          </button>
          <button
            type="button"
            data-testid={`accept-${candidate.id}`}
            onClick={() => onDecide(candidate.id, 'accepted')}
            className="rounded bg-primary px-2 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90"
          >
            Accept
          </button>
        </div>
      )}
    </div>
  );
}

export function CorrelationPanel(
  props: CorrelationPanelProps,
): React.ReactElement {
  const { candidates, isLoading, isScanning, onScan, onDecide } = props;

  if (isLoading) {
    return (
      <div
        data-testid="correlation-panel"
        className="flex h-32 items-center justify-center text-sm text-muted-foreground"
      >
        Loading correlations…
      </div>
    );
  }

  if (candidates.length === 0) {
    return (
      <div
        data-testid="correlation-panel"
        className="flex h-32 flex-col items-center justify-center gap-2 text-sm text-muted-foreground"
      >
        <p>No correlation candidates yet.</p>
        {onScan && (
          <button
            type="button"
            data-testid="scan-empty"
            onClick={onScan}
            disabled={isScanning}
            className="rounded bg-primary px-3 py-1 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {isScanning ? 'Scanning…' : 'Run correlation scan'}
          </button>
        )}
      </div>
    );
  }

  return (
    <div data-testid="correlation-panel" className="space-y-2">
      {onScan && (
        <div className="flex justify-end">
          <button
            type="button"
            data-testid="scan-existing"
            onClick={onScan}
            disabled={isScanning}
            className="rounded border border-border px-2 py-1 text-xs text-muted-foreground hover:bg-accent/30 disabled:opacity-50"
          >
            {isScanning ? 'Scanning…' : 'Rescan'}
          </button>
        </div>
      )}
      {candidates.map((c) => (
        <CandidateRow key={c.id} candidate={c} onDecide={onDecide} />
      ))}
    </div>
  );
}
