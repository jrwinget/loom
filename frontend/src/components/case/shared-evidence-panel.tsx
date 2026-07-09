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
            className="bg-muted h-16 animate-pulse rounded-lg"
          />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section>
        <h3 className="text-muted-foreground mb-3 text-sm font-semibold tracking-wider uppercase">
          Incoming Shared Evidence
        </h3>
        {incoming.length === 0 ? (
          <p
            data-testid="no-incoming"
            className="text-muted-foreground text-sm"
          >
            No evidence shared to this case
          </p>
        ) : (
          <ul className="space-y-2">
            {incoming.map((item) => (
              <li
                key={item.id}
                data-testid="shared-item"
                className="border-border bg-card flex items-center justify-between rounded-md border p-3"
              >
                <div>
                  <span className="text-foreground text-sm font-medium">
                    {item.originalFilename ?? 'Unknown file'}
                  </span>
                  <span className="bg-muted text-muted-foreground ml-2 rounded px-1.5 py-0.5 text-xs">
                    {item.accessLevel}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h3 className="text-muted-foreground mb-3 text-sm font-semibold tracking-wider uppercase">
          Outgoing Shared Evidence
        </h3>
        {outgoing.length === 0 ? (
          <p
            data-testid="no-outgoing"
            className="text-muted-foreground text-sm"
          >
            No evidence shared from this case
          </p>
        ) : (
          <ul className="space-y-2">
            {outgoing.map((item) => (
              <li
                key={item.id}
                data-testid="shared-item"
                className="border-border bg-card flex items-center justify-between rounded-md border p-3"
              >
                <div>
                  <span className="text-foreground text-sm font-medium">
                    {item.originalFilename ?? 'Unknown file'}
                  </span>
                  <span className="bg-muted text-muted-foreground ml-2 rounded px-1.5 py-0.5 text-xs">
                    {item.accessLevel}
                  </span>
                </div>
                <button
                  data-testid="revoke-btn"
                  onClick={() => onRevoke(item.id)}
                  className="text-destructive hover:bg-destructive/10 rounded-md px-3 py-1 text-xs"
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
