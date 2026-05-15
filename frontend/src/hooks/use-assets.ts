import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuthStore } from '@/stores/auth-store';
import { queryKeys } from '@/lib/query-keys';
import { apiClient, getApiOrigin } from '@/lib/api-client';
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

export function useAsset(assetId: string): ReturnType<typeof useQuery<Asset>> {
  return useQuery({
    queryKey: queryKeys.assets.detail(assetId),
    queryFn: () => apiClient.get<Asset>(`/assets/${assetId}`),
    enabled: !!assetId,
  });
}

interface UploadAssetVars {
  file: File;
  onProgress?: (pct: number) => void;
}

export function useUploadAsset(
  caseId: string,
): ReturnType<typeof useMutation<Asset, Error, UploadAssetVars>> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ file, onProgress }: UploadAssetVars) => {
      const token = useAuthStore.getState().token;
      const formData = new FormData();
      formData.append('file', file);

      return new Promise<Asset>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', `${getApiOrigin()}/cases/${caseId}/assets`);

        if (token) {
          xhr.setRequestHeader('Authorization', `Bearer ${token}`);
        }

        xhr.upload.addEventListener('progress', (e) => {
          if (e.lengthComputable && onProgress) {
            onProgress(Math.round((e.loaded / e.total) * 100));
          }
        });

        xhr.addEventListener('load', () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            try {
              resolve(JSON.parse(xhr.responseText) as Asset);
            } catch {
              reject(new Error('Invalid response from server'));
            }
          } else {
            reject(new Error(`Upload failed: ${xhr.statusText}`));
          }
        });

        xhr.addEventListener('error', () => {
          reject(new Error('Upload network error'));
        });

        xhr.send(formData);
      });
    },
    onSuccess: () => {
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
        `/cases/${caseId}/assets/${assetId}/download`,
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
