import { useCallback, useState } from 'react';
import {
  useAcceptCluster,
  useMergeClusters,
  useRejectCluster,
} from '@/hooks/use-clusters';
import type { EventCluster, ClusterItem } from '@/types/cluster';

interface ClusterReviewProps {
  caseId: string;
  clusters: EventCluster[];
}

const STATUS_COLORS: Record<string, string> = {
  proposed: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200',
  accepted: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200',
  rejected: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200',
};

// group items by asset id for display
function groupByAsset(items: ClusterItem[]): Record<string, ClusterItem[]> {
  const groups: Record<string, ClusterItem[]> = {};
  for (const item of items) {
    const key = item.assetId;
    if (!groups[key]) groups[key] = [];
    groups[key].push(item);
  }
  return groups;
}

function ContentTypeBadge(props: { contentType: string }): React.ReactElement {
  const { contentType } = props;
  const label = contentType.split('/')[0] ?? contentType;
  return (
    <span
      data-testid="content-type-badge"
      className="bg-muted text-muted-foreground inline-flex rounded px-1.5 py-0.5 text-xs font-medium"
    >
      {label}
    </span>
  );
}

export function ClusterReview(props: ClusterReviewProps): React.ReactElement {
  const { caseId, clusters } = props;
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState('');

  const acceptCluster = useAcceptCluster(caseId);
  const rejectCluster = useRejectCluster(caseId);
  const mergeClusters = useMergeClusters(caseId);

  const toggleSelect = useCallback((id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  }, []);

  const handleAccept = useCallback(
    (cluster: EventCluster) => {
      if (editingId === cluster.id) {
        // submit the accept
        acceptCluster.mutate({
          clusterId: cluster.id,
          payload: { title: editTitle || undefined },
        });
        setEditingId(null);
        setEditTitle('');
      } else {
        // open title edit
        setEditingId(cluster.id);
        setEditTitle(cluster.proposedTitle);
      }
    },
    [editingId, editTitle, acceptCluster],
  );

  const handleReject = useCallback(
    (clusterId: string) => {
      rejectCluster.mutate(clusterId);
    },
    [rejectCluster],
  );

  const handleMerge = useCallback(() => {
    const ids = Array.from(selected);
    if (ids.length < 2) return;
    mergeClusters.mutate(ids);
    setSelected(new Set());
  }, [selected, mergeClusters]);

  if (clusters.length === 0) {
    return (
      <div
        data-testid="clusters-empty"
        className="border-border flex h-48 items-center justify-center rounded-lg border border-dashed"
      >
        <p className="text-muted-foreground text-sm">No clusters to review</p>
      </div>
    );
  }

  return (
    <div data-testid="cluster-review" className="space-y-4">
      {/* merge action */}
      {selected.size >= 2 && (
        <div className="flex items-center gap-2">
          <button
            type="button"
            data-testid="merge-clusters-btn"
            onClick={handleMerge}
            disabled={mergeClusters.isPending}
            className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-md px-3 py-1.5 text-sm disabled:opacity-50"
          >
            {mergeClusters.isPending
              ? 'Merging...'
              : `Merge ${selected.size} clusters`}
          </button>
        </div>
      )}

      {clusters.map((cluster) => {
        const grouped = groupByAsset(cluster.items);
        const isEditing = editingId === cluster.id;

        return (
          <div
            key={cluster.id}
            data-testid={`cluster-card-${cluster.id}`}
            className="border-border rounded-lg border p-4"
          >
            {/* header row */}
            <div className="flex items-start justify-between gap-2">
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={selected.has(cluster.id)}
                  onChange={() => toggleSelect(cluster.id)}
                  className="border-border h-4 w-4 rounded"
                  aria-label={`Select cluster ${cluster.proposedTitle}`}
                />
                <div>
                  {isEditing ? (
                    <input
                      type="text"
                      value={editTitle}
                      onChange={(e) => setEditTitle(e.target.value)}
                      data-testid="cluster-title-edit"
                      className="border-border bg-background text-foreground rounded border px-2 py-1 text-sm"
                    />
                  ) : (
                    <h3 className="text-foreground text-sm font-semibold">
                      {cluster.proposedTitle}
                    </h3>
                  )}
                  <p className="text-muted-foreground text-xs">
                    {new Date(cluster.timeWindowStart).toLocaleString()}
                    {' \u2014 '}
                    {new Date(cluster.timeWindowEnd).toLocaleString()}
                    {' \u00b7 '}
                    {cluster.items.length} item
                    {cluster.items.length !== 1 ? 's' : ''}
                  </p>
                </div>
              </div>
              <span
                data-testid="cluster-status-badge"
                className={`rounded-full px-2 py-0.5 text-xs font-medium ${
                  STATUS_COLORS[cluster.status] ?? ''
                }`}
              >
                {cluster.status}
              </span>
            </div>

            {/* items grouped by asset */}
            <div className="mt-3 space-y-2">
              {Object.entries(grouped).map(([assetId, items]) => (
                <div
                  key={assetId}
                  data-testid={`asset-group-${assetId}`}
                  className="bg-muted/30 rounded p-2"
                >
                  <p className="text-muted-foreground text-xs font-medium">
                    {items[0].originalFilename}
                  </p>
                  <div className="mt-1 space-y-1">
                    {items.map((item) => (
                      <div
                        key={item.id}
                        data-testid={`cluster-item-${item.id}`}
                        className="flex items-center gap-2 text-xs"
                      >
                        <ContentTypeBadge contentType={item.contentType} />
                        <span className="text-muted-foreground">
                          {new Date(
                            item.absoluteTimeStart,
                          ).toLocaleTimeString()}
                        </span>
                        {item.textPreview && (
                          <span className="text-foreground truncate">
                            {item.textPreview}
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            {/* actions */}
            {cluster.status === 'proposed' && (
              <div className="mt-3 flex gap-2">
                <button
                  type="button"
                  data-testid="accept-cluster-btn"
                  onClick={() => handleAccept(cluster)}
                  disabled={acceptCluster.isPending}
                  className="rounded-md bg-green-600 px-3 py-1.5 text-sm text-white hover:bg-green-700 disabled:opacity-50"
                >
                  {isEditing ? 'Confirm' : 'Accept'}
                </button>
                <button
                  type="button"
                  data-testid="reject-cluster-btn"
                  onClick={() => handleReject(cluster.id)}
                  disabled={rejectCluster.isPending}
                  className="rounded-md bg-gray-200 px-3 py-1.5 text-sm text-gray-800 hover:bg-gray-300 disabled:opacity-50"
                >
                  Reject
                </button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
