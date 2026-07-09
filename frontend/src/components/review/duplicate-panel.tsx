import { useState, useCallback } from 'react';
import type {
  DuplicateCluster,
  DuplicateClusterMember,
} from '@/types/transcript';

interface DuplicatePanelProps {
  clusters: DuplicateCluster[];
  onMarkPrimary?: (clusterId: string, assetId: string) => void;
  onUpdateStatus?: (clusterId: string, status: string) => void;
}

const statusBadgeColors: Record<string, string> = {
  pending:
    'bg-yellow-100 text-yellow-800 ' +
    'dark:bg-yellow-900 dark:text-yellow-200',
  reviewed:
    'bg-green-100 text-green-800 ' + 'dark:bg-green-900 dark:text-green-200',
  dismissed:
    'bg-gray-100 text-gray-600 ' + 'dark:bg-gray-800 dark:text-gray-400',
};

function MemberRow(props: {
  member: DuplicateClusterMember;
  onMarkPrimary?: () => void;
}): React.ReactElement {
  const { member, onMarkPrimary } = props;
  return (
    <div
      data-testid={`member-${member.id}`}
      className="flex items-center gap-2 px-3 py-1.5 text-sm"
    >
      <span className="text-foreground flex-1 truncate">
        {member.originalFilename}
      </span>
      {member.distance !== null && (
        <span className="text-muted-foreground text-xs">
          d={member.distance.toFixed(3)}
        </span>
      )}
      {member.isPrimary ? (
        <span className="bg-primary/10 text-primary rounded px-1.5 py-0.5 text-xs font-medium">
          Primary
        </span>
      ) : (
        onMarkPrimary && (
          <button
            type="button"
            onClick={onMarkPrimary}
            className="border-border text-muted-foreground hover:bg-accent/30 rounded border px-1.5 py-0.5 text-xs"
          >
            Set primary
          </button>
        )
      )}
    </div>
  );
}

export function DuplicatePanel(props: DuplicatePanelProps): React.ReactElement {
  const { clusters, onMarkPrimary, onUpdateStatus } = props;

  const [expandedId, setExpandedId] = useState<string | null>(null);

  const toggle = useCallback((id: string) => {
    setExpandedId((prev) => (prev === id ? null : id));
  }, []);

  if (clusters.length === 0) {
    return (
      <div
        data-testid="duplicate-panel"
        className="text-muted-foreground flex h-32 items-center justify-center text-sm"
      >
        No duplicate clusters found
      </div>
    );
  }

  return (
    <div data-testid="duplicate-panel" className="space-y-2">
      {clusters.map((cluster) => {
        const isExpanded = expandedId === cluster.id;
        const badgeColor =
          statusBadgeColors[cluster.status] ?? statusBadgeColors.pending;

        return (
          <div
            key={cluster.id}
            data-testid={`cluster-${cluster.id}`}
            className="border-border rounded border"
          >
            {/* cluster header */}
            <button
              type="button"
              onClick={() => toggle(cluster.id)}
              aria-expanded={isExpanded}
              className="hover:bg-accent/30 flex w-full items-center gap-2 px-3 py-2 text-left"
            >
              <span className="text-foreground text-sm font-medium">
                {cluster.members.length} files
              </span>
              <span
                data-testid="status-badge"
                className={`rounded-full px-2 py-0.5 text-xs font-medium ${badgeColor}`}
              >
                {cluster.status}
              </span>
              <span className="text-muted-foreground ml-auto text-xs">
                {isExpanded ? '▲' : '▼'}
              </span>
            </button>

            {/* expanded members */}
            {isExpanded && (
              <div className="border-border border-t">
                {cluster.members.map((member) => (
                  <MemberRow
                    key={member.id}
                    member={member}
                    onMarkPrimary={
                      onMarkPrimary
                        ? () => onMarkPrimary(cluster.id, member.assetId)
                        : undefined
                    }
                  />
                ))}

                {/* status controls */}
                {onUpdateStatus && (
                  <div className="border-border flex gap-2 border-t px-3 py-2">
                    <button
                      type="button"
                      data-testid="mark-reviewed"
                      onClick={() => onUpdateStatus(cluster.id, 'reviewed')}
                      className="rounded bg-green-600 px-2 py-0.5 text-xs font-medium text-white"
                    >
                      Mark Reviewed
                    </button>
                    <button
                      type="button"
                      data-testid="dismiss-cluster"
                      onClick={() => onUpdateStatus(cluster.id, 'dismissed')}
                      className="rounded bg-gray-500 px-2 py-0.5 text-xs font-medium text-white"
                    >
                      Dismiss
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
