import { useParams } from 'react-router-dom';
import { useAsset, useAssetDownloadUrl } from '@/hooks/use-assets';
import { QueryError } from '@/components/layout/query-error';
import { useCapabilities } from '@/hooks/use-capabilities';
import { useTranscript, useStartTranscription } from '@/hooks/use-transcript';
import { useScenes, useStartSceneDetection } from '@/hooks/use-scenes';
import { ReviewWorkspace } from '@/components/review/review-workspace';

export function ReviewPage(): React.ReactElement {
  const { caseId, assetId } = useParams<{
    caseId: string;
    assetId: string;
  }>();

  const safeCase = caseId ?? '';
  const safeAsset = assetId ?? '';

  const {
    data: asset,
    isLoading: assetLoading,
    isError: assetError,
    refetch: refetchAsset,
  } = useAsset(safeCase, safeAsset);
  const { data: assetSrc } = useAssetDownloadUrl(safeCase, safeAsset);
  const {
    data: transcript,
    isLoading: transcriptLoading,
    isError: transcriptError,
  } = useTranscript(safeCase, safeAsset);
  const {
    data: scenes,
    isLoading: scenesLoading,
    isError: scenesError,
  } = useScenes(safeCase, safeAsset);

  const startTranscription = useStartTranscription(
    safeCase,
    safeAsset,
    asset?.originalFilename,
  );
  const startSceneDetection = useStartSceneDetection(
    safeCase,
    safeAsset,
    asset?.originalFilename,
  );
  const { data: capabilities } = useCapabilities();

  // gate only on a confirmed "missing" — while capabilities load,
  // buttons stay enabled and the backend remains the authority
  const engines = capabilities?.engines;
  const canTranscribe =
    !engines ||
    engines.transcriptionLocal.status === 'available' ||
    engines.transcriptionCloud.status === 'available';
  const transcribeRemedy = engines?.transcriptionLocal.remedy ?? undefined;
  const canDetectScenes =
    !engines || engines.sceneDetection.status === 'available';
  const scenesRemedy = engines?.sceneDetection.remedy ?? undefined;

  // error state
  if (assetError) {
    return (
      <div className="p-6">
        <QueryError
          message="Failed to load asset."
          onRetry={() => void refetchAsset()}
        />
      </div>
    );
  }

  // loading state
  if (assetLoading || !asset) {
    return (
      <div aria-busy="true" className="flex h-full items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading asset...</p>
      </div>
    );
  }

  // action buttons for missing data
  const actions = (
    <div className="flex gap-2 px-4 py-2">
      {(transcriptError ||
        (!transcriptLoading && !transcript?.segments.length)) && (
        <button
          type="button"
          data-testid="start-transcription"
          onClick={() => startTranscription.mutate()}
          disabled={startTranscription.isPending || !canTranscribe}
          title={canTranscribe ? undefined : transcribeRemedy}
          className="rounded bg-primary px-3 py-1 text-xs font-medium text-primary-foreground disabled:opacity-50"
        >
          {startTranscription.isPending ? 'Starting...' : 'Start Transcription'}
        </button>
      )}
      {(scenesError || (!scenesLoading && !scenes?.length)) && (
        <button
          type="button"
          data-testid="start-scene-detection"
          onClick={() => startSceneDetection.mutate()}
          disabled={startSceneDetection.isPending || !canDetectScenes}
          title={canDetectScenes ? undefined : scenesRemedy}
          className="rounded bg-primary px-3 py-1 text-xs font-medium text-primary-foreground disabled:opacity-50"
        >
          {startSceneDetection.isPending
            ? 'Starting...'
            : 'Start Scene Detection'}
        </button>
      )}
    </div>
  );

  return (
    <div className="flex h-full flex-col">
      {/* action buttons if data is missing */}
      {actions}

      {/* workspace */}
      <div className="flex-1 overflow-hidden">
        <ReviewWorkspace
          caseId={safeCase}
          asset={asset}
          assetSrc={assetSrc ?? ''}
          segments={transcript?.segments ?? []}
          scenes={scenes ?? []}
        />
      </div>
    </div>
  );
}
