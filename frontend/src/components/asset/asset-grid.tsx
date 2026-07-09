import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import type { Asset, MediaType } from '@/types/asset';

interface AssetGridProps {
  assets: Asset[];
  loading?: boolean;
  onSelect: (asset: Asset) => void;
}

type SortField = 'createdAt' | 'originalFilename' | 'mediaType';

const mediaTypeIcons: Record<MediaType, string> = {
  video: 'V',
  image: 'I',
  audio: 'A',
  document: 'D',
  other: '?',
};

const mediaTypeBadgeColors: Record<MediaType, string> = {
  video:
    'bg-purple-100 text-purple-800 ' +
    'dark:bg-purple-900 dark:text-purple-200',
  image: 'bg-blue-100 text-blue-800 ' + 'dark:bg-blue-900 dark:text-blue-200',
  audio:
    'bg-yellow-100 text-yellow-800 ' +
    'dark:bg-yellow-900 dark:text-yellow-200',
  document:
    'bg-green-100 text-green-800 ' + 'dark:bg-green-900 dark:text-green-200',
  other: 'bg-gray-100 text-gray-800 ' + 'dark:bg-gray-900 dark:text-gray-200',
};

const processingStatusColors: Record<string, string> = {
  pending: 'bg-yellow-500',
  processing: 'bg-blue-500 animate-pulse',
  complete: 'bg-green-500',
  failed: 'bg-red-500',
};

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const val = bytes / Math.pow(k, i);
  return `${val.toFixed(1)} ${sizes[i]}`;
}

const allMediaTypes: MediaType[] = [
  'video',
  'image',
  'audio',
  'document',
  'other',
];

function SkeletonCard(): React.ReactElement {
  return (
    <div
      data-testid="skeleton-card"
      className="border-border bg-card flex animate-pulse flex-col rounded-lg border p-4"
    >
      <div className="bg-muted mb-3 flex h-24 items-center justify-center rounded" />
      <div className="bg-muted h-4 w-3/4 rounded" />
      <div className="bg-muted mt-2 h-3 w-1/2 rounded" />
    </div>
  );
}

export function AssetGrid(props: AssetGridProps): React.ReactElement {
  const { assets, loading = false, onSelect } = props;

  const [sortField, setSortField] = useState<SortField>('createdAt');
  const [filterType, setFilterType] = useState<MediaType | 'all'>('all');

  const filtered = useMemo(() => {
    let result = assets;
    if (filterType !== 'all') {
      result = result.filter((a) => a.mediaType === filterType);
    }
    return [...result].sort((a, b) => {
      if (sortField === 'createdAt') {
        return (
          new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime()
        );
      }
      if (sortField === 'originalFilename') {
        return a.originalFilename.localeCompare(b.originalFilename);
      }
      return a.mediaType.localeCompare(b.mediaType);
    });
  }, [assets, sortField, filterType]);

  // loading state
  if (loading) {
    return (
      <div
        data-testid="asset-grid"
        aria-busy="true"
        aria-label="Loading assets"
        className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4"
      >
        {Array.from({ length: 8 }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    );
  }

  // empty state
  if (assets.length === 0) {
    return (
      <div
        data-testid="asset-grid-empty"
        className="border-border flex h-48 items-center justify-center rounded-lg border border-dashed"
      >
        <p className="text-muted-foreground text-sm">No assets uploaded yet</p>
      </div>
    );
  }

  return (
    <div data-testid="asset-grid">
      {/* controls row */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        {/* sort */}
        <label htmlFor="asset-sort" className="text-muted-foreground text-xs">
          Sort by
        </label>
        <select
          id="asset-sort"
          data-testid="sort-select"
          value={sortField}
          onChange={(e) => setSortField(e.target.value as SortField)}
          className="border-border bg-card text-foreground rounded border px-2 py-1 text-xs"
        >
          <option value="createdAt">Upload date</option>
          <option value="originalFilename">Filename</option>
          <option value="mediaType">Media type</option>
        </select>

        {/* filter */}
        <label htmlFor="asset-filter" className="text-muted-foreground text-xs">
          Filter
        </label>
        <select
          id="asset-filter"
          data-testid="filter-select"
          value={filterType}
          onChange={(e) => setFilterType(e.target.value as MediaType | 'all')}
          className="border-border bg-card text-foreground rounded border px-2 py-1 text-xs"
        >
          <option value="all">All types</option>
          {allMediaTypes.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </select>
      </div>

      {/* grid */}
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
        {filtered.map((asset) => (
          <button
            key={asset.id}
            type="button"
            data-testid={`asset-card-${asset.id}`}
            onClick={() => onSelect(asset)}
            className="border-border bg-card hover:bg-accent/50 flex flex-col rounded-lg border p-4 text-left shadow-xs transition-colors"
          >
            {/* thumbnail placeholder */}
            <div className="bg-muted text-muted-foreground mb-3 flex h-24 items-center justify-center rounded text-2xl font-bold">
              {mediaTypeIcons[asset.mediaType]}
            </div>

            {/* filename */}
            <p
              className="text-foreground truncate text-sm font-medium"
              data-testid="asset-filename"
            >
              {asset.originalFilename}
            </p>

            {/* meta row */}
            <div className="mt-2 flex items-center gap-2">
              {/* media type badge */}
              <span
                data-testid="media-type-badge"
                className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${
                  mediaTypeBadgeColors[asset.mediaType]
                }`}
              >
                {asset.mediaType}
              </span>

              {/* file size */}
              <span className="text-muted-foreground text-xs">
                {formatBytes(asset.fileSizeBytes)}
              </span>

              {/* processing status dot */}
              <span
                data-testid="processing-status"
                title={asset.processingStatus}
                role="status"
                aria-label={`Processing: ${asset.processingStatus}`}
                className={`ml-auto h-2 w-2 rounded-full ${
                  processingStatusColors[asset.processingStatus] ??
                  'bg-gray-500'
                }`}
              />
            </div>

            {/* review link */}
            <Link
              to={`/cases/${asset.caseId}` + `/review/${asset.id}`}
              data-testid={`review-link-${asset.id}`}
              onClick={(e) => e.stopPropagation()}
              className="bg-primary/10 text-primary hover:bg-primary/20 mt-2 inline-flex items-center rounded px-2 py-0.5 text-xs font-medium"
            >
              Review
            </Link>
          </button>
        ))}
      </div>
    </div>
  );
}
