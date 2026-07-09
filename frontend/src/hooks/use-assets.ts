import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '@/stores/auth-store';
import { queryKeys } from '@/lib/query-keys';
import { apiClient, camelizeKeys, getApiOrigin } from '@/lib/api-client';
import { useJobStore } from '@/stores/job-store';
import { useToastStore } from '@/stores/toast-store';
import type { Asset, AssetListResponse } from '@/types/asset';

export function useAssets(
  caseId: string,
): ReturnType<typeof useQuery<Asset[]>> {
  return useQuery({
    queryKey: queryKeys.assets.byCase(caseId),
    queryFn: async () => {
      const res = await apiClient.get<AssetListResponse>(
        `/cases/${caseId}/assets`,
      );
      return res.items;
    },
    enabled: !!caseId,
  });
}

export function useAsset(
  caseId: string,
  assetId: string,
): ReturnType<typeof useQuery<Asset>> {
  return useQuery({
    queryKey: queryKeys.assets.detail(assetId),
    queryFn: () => apiClient.get<Asset>(`/cases/${caseId}/assets/${assetId}`),
    enabled: !!caseId && !!assetId,
  });
}

interface UploadAssetVars {
  file: File;
  onProgress?: (pct: number) => void;
}

// surface the backend's detail message instead of the http status text
function uploadErrorDetail(xhr: XMLHttpRequest): string {
  try {
    const body = JSON.parse(xhr.responseText) as { detail?: unknown };
    if (typeof body.detail === 'string' && body.detail) {
      return body.detail;
    }
  } catch {
    // non-json body; fall through to the generic message
  }
  return `Upload failed (${xhr.status || 'network'})`;
}

// shared raw-xhr upload used by both the single-file mutation and the
// dropzone batch flow. fetch can't report upload progress, hence xhr;
// keep the route a literal template so the contract test extracts it.
// the raw File body streams through the streaming route, so the
// backend never buffers the file in memory and the cap is the
// configured limit rather than a multipart-parser ceiling.
export function uploadAssetXhr(
  caseId: string,
  file: File,
  onProgress?: (pct: number) => void,
): Promise<Asset> {
  const token = useAuthStore.getState().token;

  return new Promise<Asset>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(
      'POST',
      `${getApiOrigin()}/cases/${caseId}/assets/upload-stream` +
        `?filename=${encodeURIComponent(file.name)}`,
    );

    if (token) {
      xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    }
    xhr.setRequestHeader('Content-Type', 'application/octet-stream');

    xhr.upload.addEventListener('progress', (e) => {
      if (e.lengthComputable && onProgress) {
        onProgress(Math.round((e.loaded / e.total) * 100));
      }
    });

    xhr.addEventListener('load', () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(camelizeKeys(JSON.parse(xhr.responseText)) as Asset);
        } catch {
          reject(new Error('Invalid response from server'));
        }
      } else {
        reject(new Error(uploadErrorDetail(xhr)));
      }
    });

    xhr.addEventListener('error', () => {
      reject(new Error('Upload network error'));
    });

    xhr.send(file);
  });
}

// track the post-upload ingest pipeline in the jobs menu; its
// workflow id is deterministic (ingest-{asset id})
export function registerIngestJob(caseId: string, asset: Asset): void {
  useJobStore.getState().registerJob({
    workflowId: `ingest-${asset.id}`,
    caseId,
    kind: 'ingest',
    label: asset.originalFilename,
    assetId: asset.id,
  });
}

export function useUploadAsset(
  caseId: string,
): ReturnType<typeof useMutation<Asset, Error, UploadAssetVars>> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ file, onProgress }: UploadAssetVars) =>
      uploadAssetXhr(caseId, file, onProgress),
    onSuccess: (asset) => {
      registerIngestJob(caseId, asset);
      void queryClient.invalidateQueries({
        queryKey: queryKeys.assets.byCase(caseId),
      });
      useToastStore.getState().addToast({
        type: 'success',
        message: 'Asset uploaded',
      });
    },
    onError: (error: Error) => {
      useToastStore.getState().addToast({
        type: 'error',
        message: error.message || 'Asset upload failed',
      });
    },
  });
}

interface DownloadUrlResponse {
  url: string;
}

export function useAssetDownloadUrl(
  caseId: string,
  assetId: string,
): ReturnType<typeof useQuery<string>> {
  return useQuery({
    queryKey: [...queryKeys.assets.detail(assetId), 'download'],
    queryFn: async () => {
      const res = await apiClient.get<DownloadUrlResponse>(
        `/cases/${caseId}/assets/${assetId}/download-url`,
      );
      return res.url;
    },
    enabled: !!caseId && !!assetId,
    // presigned urls expire after 15 minutes server-side. mark
    // stale at 10 minutes so an open detail view auto-refetches a
    // fresh URL before the current one expires; gcTime keeps the
    // cached URL around long enough to avoid spurious refetches
    // during navigation.
    staleTime: 10 * 60_000,
    gcTime: 15 * 60_000,
  });
}
