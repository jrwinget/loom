import {
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import { useAuthStore } from '@/stores/auth-store';
import { queryKeys } from '@/lib/query-keys';
import { apiClient } from '@/lib/api-client';
import type {
  Asset,
  AssetListResponse,
} from '@/types/asset';

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
  assetId: string,
): ReturnType<typeof useQuery<Asset>> {
  return useQuery({
    queryKey: queryKeys.assets.detail(assetId),
    queryFn: () =>
      apiClient.get<Asset>(`/assets/${assetId}`),
    enabled: !!assetId,
  });
}

interface UploadAssetVars {
  file: File;
  onProgress?: (pct: number) => void;
}

export function useUploadAsset(
  caseId: string,
): ReturnType<
  typeof useMutation<Asset, Error, UploadAssetVars>
> {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async ({ file, onProgress }: UploadAssetVars) => {
      const token = useAuthStore.getState().token;
      const formData = new FormData();
      formData.append('file', file);

      return new Promise<Asset>((resolve, reject) => {
        const xhr = new XMLHttpRequest();
        xhr.open(
          'POST',
          `/api/v1/cases/${caseId}/assets`,
        );

        if (token) {
          xhr.setRequestHeader(
            'Authorization',
            `Bearer ${token}`,
          );
        }

        xhr.upload.addEventListener('progress', (e) => {
          if (e.lengthComputable && onProgress) {
            onProgress(
              Math.round((e.loaded / e.total) * 100),
            );
          }
        });

        xhr.addEventListener('load', () => {
          if (xhr.status >= 200 && xhr.status < 300) {
            resolve(
              JSON.parse(xhr.responseText) as Asset,
            );
          } else {
            reject(
              new Error(
                `Upload failed: ${xhr.statusText}`,
              ),
            );
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
    queryKey: [
      ...queryKeys.assets.detail(assetId),
      'download',
    ],
    queryFn: async () => {
      const res =
        await apiClient.get<DownloadUrlResponse>(
          `/cases/${caseId}/assets/${assetId}/download`,
        );
      return res.url;
    },
    enabled: !!caseId && !!assetId,
    // presigned urls expire, refetch often
    staleTime: 60_000,
  });
}
