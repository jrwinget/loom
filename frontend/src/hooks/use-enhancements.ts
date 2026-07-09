import { useCallback } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import { queryKeys } from '@/lib/query-keys';
import { useJobStore } from '@/stores/job-store';
import type { AiProvenance } from '@/types/transcript';

// deterministic ffmpeg filter parameters; defaults are all neutral.
// scaleFactor is camelCase here but sent to the backend as
// scale_factor (request bodies are not camelCase-transformed).
export interface EnhancementParams {
  brightness: number;
  contrast: number;
  saturation: number;
  gamma: number;
  denoise: number;
  sharpen: number;
  deinterlace: boolean;
  scaleFactor: number;
}

export const NEUTRAL_PARAMS: EnhancementParams = {
  brightness: 0,
  contrast: 1,
  saturation: 1,
  gamma: 1,
  denoise: 0,
  sharpen: 0,
  deinterlace: false,
  scaleFactor: 1,
};

export interface EnhancementDerivative {
  id: string;
  // the api-client camelCases the free-form provenance blob, so it
  // arrives shaped exactly like the WhyPopover props
  generationParams: AiProvenance | null;
  createdAt: string;
  downloadUrl: string;
}

interface EnhancementListResponse {
  enhancements: EnhancementDerivative[];
}

export interface EnhancementSuggestion {
  params: EnhancementParams;
  reasons: string[];
}

interface EnhancementCreatedResponse {
  workflowId: string;
  status: string;
  params: EnhancementParams;
}

// request bodies are sent verbatim, so map the single camelCase field
// back to the snake_case the backend schema validates
function toWire(params: EnhancementParams): Record<string, unknown> {
  return {
    brightness: params.brightness,
    contrast: params.contrast,
    saturation: params.saturation,
    gamma: params.gamma,
    denoise: params.denoise,
    sharpen: params.sharpen,
    deinterlace: params.deinterlace,
    scale_factor: params.scaleFactor,
  };
}

export function useEnhancements(
  caseId: string,
  assetId: string,
): ReturnType<typeof useQuery<EnhancementDerivative[]>> {
  return useQuery({
    queryKey: queryKeys.enhancements.byAsset(caseId, assetId),
    queryFn: async () => {
      const res = await apiClient.get<EnhancementListResponse>(
        `/cases/${caseId}/assets/${assetId}/enhancements`,
      );
      return res.enhancements;
    },
    enabled: !!caseId && !!assetId,
  });
}

export function useSuggestEnhancement(
  caseId: string,
  assetId: string,
): ReturnType<typeof useMutation<EnhancementSuggestion, Error, void>> {
  return useMutation({
    mutationFn: () =>
      apiClient.get<EnhancementSuggestion>(
        `/cases/${caseId}/assets/${assetId}/enhancements/suggest`,
      ),
  });
}

export function useCreateEnhancement(
  caseId: string,
  assetId: string,
  label?: string,
): ReturnType<
  typeof useMutation<EnhancementCreatedResponse, Error, EnhancementParams>
> {
  const start = useCallback(
    (params: EnhancementParams) =>
      apiClient.post<EnhancementCreatedResponse>(
        `/cases/${caseId}/assets/${assetId}/enhancements`,
        toWire(params),
      ),
    [caseId, assetId],
  );

  return useMutation({
    mutationFn: start,
    onSuccess: (data) => {
      // the jobs watcher polls this workflow and refetches the
      // enhancements list when it finishes — no premature invalidation
      const register = (workflowId: string, params: EnhancementParams): void =>
        useJobStore.getState().registerJob({
          workflowId,
          caseId,
          kind: 'enhancement',
          label: label ?? 'Enhancement',
          assetId,
          retry: () => {
            void start(params).then((next) =>
              register(next.workflowId, next.params),
            );
          },
        });
      register(data.workflowId, data.params);
    },
  });
}
