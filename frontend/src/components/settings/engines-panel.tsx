import {
  useDeleteModel,
  useDownloadModel,
  useEngines,
  type EngineInfo,
  type ModelInfo,
} from '@/hooks/use-engines';

const ENGINE_LABELS: Record<string, string> = {
  transcriptionLocal: 'On-device transcription',
  ocr: 'OCR',
  sceneDetection: 'Scene detection',
  mediaPipeline: 'Media pipeline (ffmpeg)',
  diarization: 'Speaker labels',
};

function formatBytes(bytes: number): string {
  if (bytes >= 1_000_000_000) {
    return `${(bytes / 1_000_000_000).toFixed(1)} GB`;
  }
  return `${Math.round(bytes / 1_000_000)} MB`;
}

function EngineRow(props: {
  name: string;
  info: EngineInfo;
}): React.ReactElement {
  const { name, info } = props;
  const available = info.status === 'available';
  return (
    <li
      data-testid={`engine-${name}`}
      className="flex items-start justify-between gap-3 py-2"
    >
      <div>
        <p className="text-sm font-medium text-foreground">
          {ENGINE_LABELS[name] ?? name}
        </p>
        {!available && info.remedy && (
          <p className="text-xs text-muted-foreground">{info.remedy}</p>
        )}
      </div>
      <span
        className={
          available
            ? 'rounded-full bg-green-100 px-2 py-0.5 text-xs ' +
              'text-green-800 dark:bg-green-900 dark:text-green-200'
            : 'rounded-full bg-amber-100 px-2 py-0.5 text-xs ' +
              'text-amber-800 dark:bg-amber-900 dark:text-amber-200'
        }
      >
        {available ? 'Available' : 'Unavailable'}
      </span>
    </li>
  );
}

function ModelRow(props: { model: ModelInfo }): React.ReactElement {
  const { model } = props;
  const download = useDownloadModel();
  const remove = useDeleteModel();

  const downloading = model.downloadStatus === 'downloading';
  const percent =
    downloading && model.bytesTotal
      ? Math.round(((model.bytesDone ?? 0) / model.bytesTotal) * 100)
      : null;

  return (
    <li
      data-testid={`model-${model.name}`}
      className="flex items-center justify-between gap-3 py-2"
    >
      <div className="min-w-0">
        <p className="text-sm font-medium text-foreground">
          {model.name}
          <span className="ml-2 text-xs text-muted-foreground">
            {formatBytes(model.sizeBytes)}
          </span>
        </p>
        {downloading && (
          <progress
            data-testid={`model-progress-${model.name}`}
            className="h-1.5 w-40"
            max={100}
            value={percent ?? undefined}
          />
        )}
        {model.downloadStatus === 'failed' && model.error && (
          <p role="alert" className="text-xs text-red-600 dark:text-red-400">
            {model.error}
          </p>
        )}
      </div>
      {model.downloaded ? (
        <button
          type="button"
          data-testid={`model-delete-${model.name}`}
          onClick={() => remove.mutate(model.name)}
          disabled={remove.isPending}
          className="text-sm text-muted-foreground hover:text-foreground"
        >
          Delete
        </button>
      ) : (
        <button
          type="button"
          data-testid={`model-download-${model.name}`}
          onClick={() => download.mutate(model.name)}
          disabled={downloading || download.isPending}
          className={
            'rounded bg-primary px-3 py-1 text-sm ' +
            'text-primary-foreground hover:bg-primary/90 ' +
            'disabled:opacity-50'
          }
        >
          {downloading ? 'Downloading…' : 'Download'}
        </button>
      )}
    </li>
  );
}

export function EnginesPanel(): React.ReactElement {
  const engines = useEngines();

  if (engines.isLoading) {
    return <p className="mt-6 text-sm text-muted-foreground">Loading…</p>;
  }
  if (engines.data == null) {
    return (
      <p role="alert" className="mt-6 text-sm text-muted-foreground">
        Engine status is unavailable right now.
      </p>
    );
  }

  return (
    <section data-testid="engines-panel" className="mt-8 space-y-6">
      <div>
        <h2 className="text-base font-semibold text-foreground">Engines</h2>
        <ul className="mt-2 divide-y divide-border">
          {Object.entries(engines.data.engines).map(([name, info]) => (
            <EngineRow key={name} name={name} info={info} />
          ))}
        </ul>
      </div>
      <div>
        <h2 className="text-base font-semibold text-foreground">
          Speech models
        </h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Downloading a model is the only network request on-device
          transcription ever makes, happens only when you click, and is verified
          against a pinned checksum. Models are stored in your data directory.
        </p>
        <ul className="mt-2 divide-y divide-border">
          {engines.data.models.map((model) => (
            <ModelRow key={model.name} model={model} />
          ))}
        </ul>
      </div>
    </section>
  );
}
