import {
  useApproveNarrative,
  useGenerateNarrative,
  useNarratives,
  useRejectNarrative,
  type NarrativeDraft,
} from '@/hooks/use-narratives';

interface NarrativePanelProps {
  caseId: string;
}

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function AiDraftedBadge(props: {
  narrative: NarrativeDraft;
}): React.ReactElement {
  const { narrative } = props;
  // the badge is persistent — before and after review — so an
  // ai-drafted narrative is never mistaken for verified evidence.
  const reviewed = narrative.status !== 'draft';
  return (
    <span
      data-testid="ai-drafted-badge"
      className={
        'inline-block rounded px-2 py-0.5 text-xs font-semibold ' +
        (reviewed
          ? 'bg-amber-100 text-amber-900 dark:bg-amber-900 dark:text-amber-100'
          : 'bg-red-100 text-red-900 dark:bg-red-900 dark:text-red-100')
      }
    >
      AI-DRAFTED
      {reviewed && narrative.reviewedAt
        ? ` — ${narrative.status} ${formatTimestamp(narrative.reviewedAt)}`
        : ' — unreviewed'}
    </span>
  );
}

function NarrativeCard(props: {
  caseId: string;
  narrative: NarrativeDraft;
}): React.ReactElement {
  const { caseId, narrative } = props;
  const approve = useApproveNarrative(caseId);
  const reject = useRejectNarrative(caseId);
  const pending = approve.isPending || reject.isPending;

  return (
    <li
      data-testid="narrative-card"
      className="border-border rounded-lg border p-3"
    >
      <div className="flex items-center justify-between gap-2">
        <AiDraftedBadge narrative={narrative} />
        <span className="text-muted-foreground text-xs">
          {narrative.modelName}
        </span>
      </div>
      <p className="text-foreground mt-2 text-sm whitespace-pre-wrap">
        {narrative.text}
      </p>
      {narrative.status === 'draft' && (
        <div className="mt-3 flex gap-2">
          <button
            type="button"
            data-testid="approve-narrative-btn"
            disabled={pending}
            onClick={() => approve.mutate(narrative.id)}
            className="bg-primary text-primary-foreground hover:bg-primary/90 rounded px-3 py-1.5 text-xs font-medium disabled:opacity-50"
          >
            Approve
          </button>
          <button
            type="button"
            data-testid="reject-narrative-btn"
            disabled={pending}
            onClick={() => reject.mutate(narrative.id)}
            className="border-border hover:bg-muted rounded border px-3 py-1.5 text-xs font-medium disabled:opacity-50"
          >
            Reject
          </button>
        </div>
      )}
    </li>
  );
}

/**
 * ai-drafted case narrative over the case's own chain-of-custody/audit
 * metadata — never over transcript, ocr, or annotation content. every
 * draft requires an explicit human approve/reject before it is eligible
 * for inclusion in any export bundle; the badge above never disappears,
 * even after review.
 */
export function NarrativePanel(props: NarrativePanelProps): React.ReactElement {
  const { caseId } = props;
  const narratives = useNarratives(caseId);
  const generate = useGenerateNarrative(caseId);
  const items = narratives.data ?? [];

  return (
    <div
      className="border-border mt-6 rounded-lg border p-4"
      data-testid="narrative-panel"
    >
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-foreground text-sm font-semibold">
            Case narrative
          </h3>
          <p className="text-muted-foreground mt-1 text-xs">
            An AI-drafted summary of this case&apos;s own custody and audit
            history — never of evidence content. Requires human review before it
            can appear in any export.
          </p>
        </div>
        <button
          type="button"
          data-testid="generate-narrative-btn"
          disabled={generate.isPending}
          onClick={() => generate.mutate(undefined)}
          className="bg-primary text-primary-foreground hover:bg-primary/90 shrink-0 rounded-md px-3 py-2 text-sm disabled:opacity-50"
        >
          {generate.isPending ? 'Drafting…' : 'Draft narrative'}
        </button>
      </div>

      {items.length === 0 ? (
        <p className="text-muted-foreground mt-3 text-sm">
          No narrative drafted yet.
        </p>
      ) : (
        <ul className="mt-3 space-y-3">
          {items.map((n) => (
            <NarrativeCard key={n.id} caseId={caseId} narrative={n} />
          ))}
        </ul>
      )}
    </div>
  );
}
