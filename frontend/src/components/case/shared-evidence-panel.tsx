import type { SharedEvidence } from '@/types/organization';

interface SharedEvidencePanelProps {
  incoming: SharedEvidence[];
  outgoing: SharedEvidence[];
  isLoading: boolean;
  onRevoke: (linkId: string) => void;
}

export function SharedEvidencePanel({
  incoming,
  outgoing,
  isLoading,
  onRevoke,
}: SharedEvidencePanelProps): React.ReactElement {
  if (isLoading) {
    return (
      <div data-testid="shared-loading" className="space-y-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div
            key={i}
            data-testid="shared-skeleton"
            className="h-16 animate-pulse rounded-lg bg-muted"
          />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section>
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Incoming Shared Evidence
        </h3>
        {incoming.length === 0 ? (
          <p
            data-testid="no-incoming"
            className="text-sm text-muted-foreground"
          >
            No evidence shared to this case
          </p>
        ) : (
          <ul className="space-y-2">
            {incoming.map((item) => (
              <li
                key={item.id}
                data-testid="shared-item"
                className="bg-card flex items-center justify-between rounded-md border border-border p-3"
              >
                <div>
                  <span className="text-sm font-medium text-foreground">
                    {item.originalFilename ?? 'Unknown file'}
                  </span>
                  <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
                    {item.accessLevel}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wider text-muted-foreground">
          Outgoing Shared Evidence
        </h3>
        {outgoing.length === 0 ? (
          <p
            data-testid="no-outgoing"
            className="text-sm text-muted-foreground"
          >
            No evidence shared from this case
          </p>
        ) : (
          <ul className="space-y-2">
            {outgoing.map((item) => (
              <li
                key={item.id}
                data-testid="shared-item"
                className="bg-card flex items-center justify-between rounded-md border border-border p-3"
              >
                <div>
                  <span className="text-sm font-medium text-foreground">
                    {item.originalFilename ?? 'Unknown file'}
                  </span>
                  <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
                    {item.accessLevel}
                  </span>
                </div>
                <button
                  data-testid="revoke-btn"
                  onClick={() => onRevoke(item.id)}
                  className="rounded-md px-3 py-1 text-xs text-destructive hover:bg-destructive/10"
                >
                  Revoke
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
