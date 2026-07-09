import { useState } from 'react';
import { camelizeKeys, getApiOrigin } from '@/lib/api-client';
import { useAuthStore } from '@/stores/auth-store';

export interface ImportBundleResult {
  caseId: string;
  workflowId: string;
  signatureStatus: 'signed_trusted' | 'signed_untrusted' | 'unsigned';
}

// raw-body upload of a bundle zip to the streaming import endpoint,
// mirroring uploadAssetXhr — a bundle can be large, so it must not
// route through the buffering json client.
function importBundleXhr(
  file: File,
  onProgress?: (pct: number) => void,
): Promise<ImportBundleResult> {
  const token = useAuthStore.getState().token;
  return new Promise<ImportBundleResult>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${getApiOrigin()}/imports/bundle`);
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
          resolve(
            camelizeKeys(JSON.parse(xhr.responseText)) as ImportBundleResult,
          );
        } catch {
          reject(new Error('Invalid response from server'));
        }
      } else {
        reject(new Error(importErrorDetail(xhr)));
      }
    });
    xhr.addEventListener('error', () =>
      reject(new Error('Import network error')),
    );
    xhr.send(file);
  });
}

function importErrorDetail(xhr: XMLHttpRequest): string {
  try {
    const detail = JSON.parse(xhr.responseText)?.detail;
    if (typeof detail === 'string') return detail;
  } catch {
    // fall through to the status text
  }
  if (xhr.status === 409) return 'This bundle has already been imported.';
  if (xhr.status === 422) return 'The file is not a valid Loom bundle.';
  return `Import failed (${xhr.status})`;
}

export interface UseImportBundle {
  importing: boolean;
  progress: number;
  error: string;
  run: (file: File) => Promise<ImportBundleResult | null>;
  reset: () => void;
}

export function useImportBundle(): UseImportBundle {
  const [importing, setImporting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState('');

  const run = async (file: File): Promise<ImportBundleResult | null> => {
    setError('');
    setProgress(0);
    setImporting(true);
    try {
      return await importBundleXhr(file, setProgress);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed');
      return null;
    } finally {
      setImporting(false);
    }
  };

  return {
    importing,
    progress,
    error,
    run,
    reset: () => {
      setError('');
      setProgress(0);
    },
  };
}
