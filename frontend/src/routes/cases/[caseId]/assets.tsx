import { useCallback, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useAssets } from '@/hooks/use-assets';
import { useAssetDownloadUrl } from '@/hooks/use-assets';
import { QueryError } from '@/components/layout/query-error';
import { UploadDropzone } from '@/components/asset/upload-dropzone';
import { AssetGrid } from '@/components/asset/asset-grid';
import { AssetDetail } from '@/components/asset/asset-detail';
import { AssetViewer } from '@/components/asset/asset-viewer';
import type { Asset } from '@/types/asset';

function SelectedAssetPanel(props: {
  asset: Asset;
  caseId: string;
}): React.ReactElement {
  const { asset, caseId } = props;
  const { data: downloadUrl } = useAssetDownloadUrl(caseId, asset.id);

  return (
    <div
      data-testid="asset-panel"
      className="fixed inset-y-0 right-0 z-40 flex w-full max-w-2xl flex-col overflow-y-auto border-l border-border bg-background shadow-lg"
    >
      {/* viewer */}
      {downloadUrl && (
        <div className="border-b border-border p-4">
          <AssetViewer asset={asset} src={downloadUrl} />
        </div>
      )}

      {/* detail */}
      <AssetDetail asset={asset} caseId={caseId} />
    </div>
  );
}

export function AssetsPage(): React.ReactElement {
  const { caseId } = useParams<{ caseId: string }>();
  const safeId = caseId ?? '';

  const {
    data: assets,
    isLoading,
    isError,
    refetch,
  } = useAssets(safeId);
  const [selected, setSelected] = useState<Asset | null>(null);

  const handleSelect = useCallback((asset: Asset) => {
    setSelected(asset);
  }, []);

  const handleClose = useCallback(() => {
    setSelected(null);
  }, []);

  return (
    <div className="relative flex flex-col gap-6 p-6">
      <h1 className="text-2xl font-bold text-foreground">Assets</h1>

      {/* upload zone */}
      <UploadDropzone caseId={safeId} />

      {/* error state */}
      {isError && (
        <QueryError
          message="Failed to load assets."
          onRetry={() => void refetch()}
        />
      )}

      {/* asset grid */}
      {!isError && (
        <AssetGrid
          assets={assets ?? []}
          loading={isLoading}
          onSelect={handleSelect}
        />
      )}

      {/* side panel overlay */}
      {selected && (
        <>
          {/* backdrop */}
          <button
            type="button"
            className="fixed inset-0 z-30 bg-black/30"
            onClick={handleClose}
            aria-label="Close panel"
          />
          <SelectedAssetPanel asset={selected} caseId={safeId} />
        </>
      )}
    </div>
  );
}
