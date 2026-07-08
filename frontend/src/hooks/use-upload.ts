import { useCallback, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { create } from 'zustand';
import { uploadAssetXhr } from '@/hooks/use-assets';
import { queryKeys } from '@/lib/query-keys';
import { useToastStore } from '@/stores/toast-store';

type FileStatus = 'pending' | 'uploading' | 'complete' | 'error';

export interface UploadFile {
  id: string;
  file: File;
  progress: number;
  status: FileStatus;
  error?: string;
}

interface UploadState {
  files: UploadFile[];
  addFiles: (files: FileList | File[]) => void;
  removeFile: (id: string) => void;
  updateFile: (id: string, patch: Partial<UploadFile>) => void;
  clear: () => void;
}

// unique id counter
let nextId = 0;
function uid(): string {
  nextId += 1;
  return `upload-${nextId}`;
}

export const useUploadStore = create<UploadState>((set) => ({
  files: [],
  addFiles: (incoming: FileList | File[]) => {
    const arr = Array.from(incoming);
    const newFiles: UploadFile[] = arr.map((f) => ({
      id: uid(),
      file: f,
      progress: 0,
      status: 'pending' as const,
    }));
    set((s) => ({ files: [...s.files, ...newFiles] }));
  },
  removeFile: (id: string) =>
    set((s) => ({
      files: s.files.filter((f) => f.id !== id),
    })),
  updateFile: (id: string, patch: Partial<UploadFile>) =>
    set((s) => ({
      files: s.files.map((f) => (f.id === id ? { ...f, ...patch } : f)),
    })),
  clear: () => set({ files: [] }),
}));

interface UseUploadReturn {
  files: UploadFile[];
  addFiles: (files: FileList | File[]) => void;
  removeFile: (id: string) => void;
  uploadAll: (caseId: string) => Promise<void>;
  isUploading: boolean;
  progress: number;
}

export function useUpload(): UseUploadReturn {
  const { files, addFiles, removeFile, updateFile } = useUploadStore();
  const queryClient = useQueryClient();

  // track whether an upload cycle is running
  const uploadingRef = useRef(false);

  const isUploading = files.some((f) => f.status === 'uploading');

  // overall progress
  const total = files.length;
  const progress =
    total === 0
      ? 0
      : Math.round(files.reduce((sum, f) => sum + f.progress, 0) / total);

  const uploadAll = useCallback(
    async (caseId: string) => {
      if (uploadingRef.current) return;
      uploadingRef.current = true;

      const pending = useUploadStore
        .getState()
        .files.filter((f) => f.status === 'pending');

      let succeeded = 0;
      let failed = 0;

      for (const entry of pending) {
        updateFile(entry.id, { status: 'uploading' });

        try {
          await uploadAssetXhr(caseId, entry.file, (pct) => {
            updateFile(entry.id, { progress: pct });
          });
          succeeded += 1;
          updateFile(entry.id, {
            status: 'complete',
            progress: 100,
          });
        } catch (err) {
          failed += 1;
          updateFile(entry.id, {
            status: 'error',
            error: err instanceof Error ? err.message : 'Unknown error',
          });
        }
      }

      if (succeeded > 0) {
        void queryClient.invalidateQueries({
          queryKey: queryKeys.assets.byCase(caseId),
        });
      }
      if (failed > 0) {
        useToastStore.getState().addToast({
          type: 'error',
          message: `${succeeded} uploaded, ${failed} failed`,
        });
      } else if (succeeded > 0) {
        useToastStore.getState().addToast({
          type: 'success',
          message:
            succeeded === 1 ? '1 file uploaded' : `${succeeded} files uploaded`,
        });
      }

      uploadingRef.current = false;
    },
    [updateFile, queryClient],
  );

  return {
    files,
    addFiles,
    removeFile,
    uploadAll,
    isUploading,
    progress,
  };
}
