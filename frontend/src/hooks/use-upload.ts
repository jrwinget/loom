import { useCallback, useRef } from 'react';
import { create } from 'zustand';
import { getApiOrigin } from '@/lib/api-client';

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

      const token =
        // eslint-disable-next-line @typescript-eslint/no-unnecessary-condition
        (await import('@/stores/auth-store')).useAuthStore.getState().token;

      for (const entry of pending) {
        updateFile(entry.id, { status: 'uploading' });

        try {
          const formData = new FormData();
          formData.append('file', entry.file);

          await new Promise<void>((resolve, reject) => {
            const xhr = new XMLHttpRequest();
            xhr.open('POST', `${getApiOrigin()}/cases/${caseId}/assets`);

            if (token) {
              xhr.setRequestHeader('Authorization', `Bearer ${token}`);
            }

            xhr.upload.addEventListener('progress', (e) => {
              if (e.lengthComputable) {
                const pct = Math.round((e.loaded / e.total) * 100);
                updateFile(entry.id, {
                  progress: pct,
                });
              }
            });

            xhr.addEventListener('load', () => {
              if (xhr.status >= 200 && xhr.status < 300) {
                resolve();
              } else {
                reject(new Error(`Upload failed: ${xhr.statusText}`));
              }
            });

            xhr.addEventListener('error', () => {
              reject(new Error('Upload network error'));
            });

            xhr.send(formData);
          });

          updateFile(entry.id, {
            status: 'complete',
            progress: 100,
          });
        } catch (err) {
          updateFile(entry.id, {
            status: 'error',
            error: err instanceof Error ? err.message : 'Unknown error',
          });
        }
      }

      uploadingRef.current = false;
    },
    [updateFile],
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
