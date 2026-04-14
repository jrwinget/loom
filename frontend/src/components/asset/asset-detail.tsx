import type { Asset } from '@/types/asset';
import { useAssetDownloadUrl } from '@/hooks/use-assets';
import { useAssetCustody } from '@/hooks/use-custody';
import type { CustodyEntry } from '@/hooks/use-custody';

interface AssetDetailProps {
  asset: Asset;
  caseId: string;
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const val = bytes / Math.pow(k, i);
  return `${val.toFixed(1)} ${sizes[i]}`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

const processingColors: Record<string, string> = {
  pending:
    'bg-yellow-100 text-yellow-800 ' +
    'dark:bg-yellow-900 dark:text-yellow-200',
  processing:
    'bg-blue-100 text-blue-800 ' +
    'dark:bg-blue-900 dark:text-blue-200',
  complete:
    'bg-green-100 text-green-800 ' +
    'dark:bg-green-900 dark:text-green-200',
  failed:
    'bg-red-100 text-red-800 ' +
    'dark:bg-red-900 dark:text-red-200',
};

interface MetaRowProps {
  label: string;
  value: string;
}

function MetaRow(props: MetaRowProps): React.ReactElement {
  return (
    <div className="flex justify-between py-1.5">
      <span className="text-xs text-muted-foreground">
        {props.label}
      </span>
      <span className="text-xs font-medium text-foreground">
        {props.value}
      </span>
    </div>
  );
}

function formatCustodyAction(action: string): string {
  return action.replace(/_/g, ' ');
}

function CustodyTimeline(props: {
  entries: CustodyEntry[];
}): React.ReactElement {
  return (
    <div className="space-y-3" data-testid="custody-timeline">
      {props.entries.map((entry) => (
        <div key={entry.id} className="flex items-start gap-3">
          <div
            className={
              'mt-1 h-2 w-2 flex-shrink-0 ' +
              'rounded-full bg-primary'
            }
          />
          <div>
            <p className="text-xs font-medium text-foreground">
              {formatCustodyAction(entry.action)}
            </p>
            <p className="text-xs text-muted-foreground">
              {formatDate(entry.timestamp)}
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

export function AssetDetail(
  props: AssetDetailProps,
): React.ReactElement {
  const { asset, caseId } = props;

  const { data: downloadUrl } = useAssetDownloadUrl(
    caseId,
    asset.id,
  );
  const { data: custodyData, isLoading: custodyLoading } =
    useAssetCustody(caseId, asset.id);

  const processingClass =
    processingColors[asset.processingStatus] ??
    processingColors['pending'];

  return (
    <div
      data-testid="asset-detail"
      className="flex flex-col gap-4 p-4"
    >
      <h2
        className={
          'truncate text-lg font-semibold text-foreground'
        }
      >
        {asset.originalFilename}
      </h2>

      <div className="flex items-center gap-2">
        <span
          data-testid="processing-badge"
          className={
            'inline-flex items-center rounded-full ' +
            'px-2.5 py-0.5 text-xs font-medium ' +
            processingClass
          }
        >
          {asset.processingStatus}
        </span>
      </div>

      <div className="divide-y divide-border">
        <MetaRow label="Media type" value={asset.mediaType} />
        <MetaRow label="MIME type" value={asset.mimeType} />
        <MetaRow
          label="File size"
          value={formatBytes(asset.fileSizeBytes)}
        />
        <MetaRow
          label="SHA-256"
          value={asset.sha256Hash.slice(0, 16) + '...'}
        />
        <MetaRow
          label="Uploaded"
          value={formatDate(asset.createdAt)}
        />
        {asset.captureTime && (
          <MetaRow
            label="Capture time"
            value={formatDate(asset.captureTime)}
          />
        )}
      </div>

      <div>
        <h3
          className={
            'mb-2 text-sm font-semibold text-foreground'
          }
        >
          Chain of custody
        </h3>
        {custodyLoading ? (
          <div className="animate-pulse space-y-2">
            <div className="h-4 w-3/4 rounded bg-muted" />
            <div className="h-4 w-1/2 rounded bg-muted" />
          </div>
        ) : custodyData && custodyData.items.length > 0 ? (
          <CustodyTimeline entries={custodyData.items} />
        ) : (
          <p className="text-xs text-muted-foreground">
            No custody records available.
          </p>
        )}
      </div>

      {downloadUrl && (
        <a
          href={downloadUrl}
          download={asset.originalFilename}
          data-testid="download-button"
          className={
            'inline-flex items-center justify-center ' +
            'rounded-md bg-primary px-4 py-2 text-sm ' +
            'font-medium text-primary-foreground ' +
            'hover:bg-primary/90'
          }
        >
          Download
        </a>
      )}
    </div>
  );
}
