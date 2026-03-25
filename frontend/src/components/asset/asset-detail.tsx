import type { Asset } from '@/types/asset';
import { useAssetDownloadUrl } from '@/hooks/use-assets';

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
      <span
        className="text-xs text-muted-foreground"
      >
        {props.label}
      </span>
      <span
        className="text-xs font-medium text-foreground"
      >
        {props.value}
      </span>
    </div>
  );
}

// placeholder chain of custody events
interface CustodyEvent {
  timestamp: string;
  action: string;
}

function buildCustodyEvents(
  asset: Asset,
): CustodyEvent[] {
  const events: CustodyEvent[] = [
    {
      timestamp: asset.createdAt,
      action: 'File uploaded',
    },
  ];
  if (asset.processingStatus === 'complete') {
    events.push({
      timestamp: asset.updatedAt,
      action: 'Processing completed',
    });
  }
  return events;
}

export function AssetDetail(
  props: AssetDetailProps,
): React.ReactElement {
  const { asset, caseId } = props;

  const { data: downloadUrl } = useAssetDownloadUrl(
    caseId,
    asset.id,
  );

  const custodyEvents = buildCustodyEvents(asset);

  const processingClass =
    processingColors[asset.processingStatus] ??
    processingColors['pending'];

  return (
    <div
      data-testid="asset-detail"
      className="flex flex-col gap-4 p-4"
    >
      {/* header */}
      <h2
        className="truncate text-lg font-semibold
          text-foreground"
      >
        {asset.originalFilename}
      </h2>

      {/* processing status */}
      <div className="flex items-center gap-2">
        <span
          data-testid="processing-badge"
          className={`inline-flex items-center
            rounded-full px-2.5 py-0.5 text-xs
            font-medium ${processingClass}`}
        >
          {asset.processingStatus}
        </span>
      </div>

      {/* metadata */}
      <div className="divide-y divide-border">
        <MetaRow
          label="Media type"
          value={asset.mediaType}
        />
        <MetaRow
          label="MIME type"
          value={asset.mimeType}
        />
        <MetaRow
          label="File size"
          value={formatBytes(asset.fileSizeBytes)}
        />
        <MetaRow
          label="SHA-256"
          value={
            asset.sha256Hash.slice(0, 16) + '...'
          }
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

      {/* chain of custody timeline */}
      <div>
        <h3
          className="mb-2 text-sm font-semibold
            text-foreground"
        >
          Chain of custody
        </h3>
        <div className="space-y-3">
          {custodyEvents.map((evt, i) => (
            <div
              key={i}
              className="flex items-start gap-3"
            >
              <div
                className="mt-1 h-2 w-2 flex-shrink-0
                  rounded-full bg-primary"
              />
              <div>
                <p className="text-xs font-medium text-foreground">
                  {evt.action}
                </p>
                <p className="text-xs text-muted-foreground">
                  {formatDate(evt.timestamp)}
                </p>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* download button */}
      {downloadUrl && (
        <a
          href={downloadUrl}
          download={asset.originalFilename}
          data-testid="download-button"
          className="inline-flex items-center
            justify-center rounded-md bg-primary px-4
            py-2 text-sm font-medium
            text-primary-foreground hover:bg-primary/90"
        >
          Download
        </a>
      )}
    </div>
  );
}
