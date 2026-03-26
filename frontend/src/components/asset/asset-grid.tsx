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
      className="bg-card flex animate-pulse flex-col rounded-lg border border-border p-4"
    >
      <div className="mb-3 flex h-24 items-center justify-center rounded bg-muted" />
      <div className="h-4 w-3/4 rounded bg-muted" />
      <div className="mt-2 h-3 w-1/2 rounded bg-muted" />
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
        className="flex h-48 items-center justify-center rounded-lg border border-dashed border-border"
      >
        <p className="text-sm text-muted-foreground">No assets uploaded yet</p>
      </div>
    );
  }

  return (
    <div data-testid="asset-grid">
      {/* controls row */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        {/* sort */}
        <label className="text-xs text-muted-foreground">Sort by</label>
        <select
          data-testid="sort-select"
          value={sortField}
          onChange={(e) => setSortField(e.target.value as SortField)}
          className="bg-card rounded border border-border px-2 py-1 text-xs text-foreground"
        >
          <option value="createdAt">Upload date</option>
          <option value="originalFilename">Filename</option>
          <option value="mediaType">Media type</option>
        </select>

        {/* filter */}
        <label className="text-xs text-muted-foreground">Filter</label>
        <select
          data-testid="filter-select"
          value={filterType}
          onChange={(e) => setFilterType(e.target.value as MediaType | 'all')}
          className="bg-card rounded border border-border px-2 py-1 text-xs text-foreground"
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
            className="bg-card flex flex-col rounded-lg border border-border p-4 text-left shadow-sm transition-colors hover:bg-accent/50"
          >
            {/* thumbnail placeholder */}
            <div className="mb-3 flex h-24 items-center justify-center rounded bg-muted text-2xl font-bold text-muted-foreground">
              {mediaTypeIcons[asset.mediaType]}
            </div>

            {/* filename */}
            <p
              className="truncate text-sm font-medium text-foreground"
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
              <span className="text-xs text-muted-foreground">
                {formatBytes(asset.fileSizeBytes)}
              </span>

              {/* processing status dot */}
              <span
                data-testid="processing-status"
                title={asset.processingStatus}
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
              className="mt-2 inline-flex items-center rounded bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary hover:bg-primary/20"
            >
              Review
            </Link>
          </button>
        ))}
      </div>
    </div>
  );
}
