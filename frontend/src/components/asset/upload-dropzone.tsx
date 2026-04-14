import { useCallback, useRef, useState } from 'react';
import { useUpload } from '@/hooks/use-upload';
import type { UploadFile } from '@/hooks/use-upload';

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  const val = bytes / Math.pow(k, i);
  return `${val.toFixed(1)} ${sizes[i]}`;
}

const statusLabels: Record<UploadFile['status'], string> = {
  pending: 'Pending',
  uploading: 'Uploading',
  complete: 'Complete',
  error: 'Error',
};

const statusColors: Record<UploadFile['status'], string> = {
  pending: 'text-muted-foreground',
  uploading: 'text-blue-600 dark:text-blue-400',
  complete: 'text-green-600 dark:text-green-400',
  error: 'text-red-600 dark:text-red-400',
};

interface UploadDropzoneProps {
  caseId: string;
}

export function UploadDropzone(props: UploadDropzoneProps): React.ReactElement {
  const { caseId } = props;
  const { files, addFiles, removeFile, uploadAll, isUploading } = useUpload();
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      if (e.dataTransfer.files.length > 0) {
        addFiles(e.dataTransfer.files);
      }
    },
    [addFiles],
  );

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback(() => {
    setDragOver(false);
  }, []);

  const handleBrowse = useCallback(() => {
    inputRef.current?.click();
  }, []);

  const handleFileInput = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      if (e.target.files && e.target.files.length > 0) {
        addFiles(e.target.files);
      }
    },
    [addFiles],
  );

  const handleUploadAll = useCallback(() => {
    void uploadAll(caseId);
  }, [uploadAll, caseId]);

  const hasPending = files.some((f) => f.status === 'pending');

  return (
    <div data-testid="upload-dropzone">
      {/* drop area */}
      <div
        data-testid="drop-area"
        onDrop={handleDrop}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors ${
          dragOver ? 'border-primary bg-primary/5' : 'bg-card border-border'
        }`}
      >
        <p className="text-sm text-muted-foreground">
          Drag and drop files here, or
        </p>
        <button
          type="button"
          data-testid="browse-button"
          onClick={handleBrowse}
          className="mt-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
        >
          Browse files
        </button>
        <input
          ref={inputRef}
          type="file"
          multiple
          className="hidden"
          onChange={handleFileInput}
          data-testid="file-input"
          aria-label="Select files to upload"
        />
      </div>

      {/* file list */}
      {files.length > 0 && (
        <div className="mt-4 space-y-2">
          {files.map((f) => (
            <div
              key={f.id}
              data-testid={`upload-file-${f.id}`}
              className="bg-card flex items-center gap-3 rounded-md border border-border p-3"
            >
              <div className="min-w-0 flex-1">
                <p
                  className="truncate text-sm font-medium text-foreground"
                  data-testid="file-name"
                >
                  {f.file.name}
                </p>
                <p className="text-xs text-muted-foreground">
                  {formatBytes(f.file.size)}
                </p>
              </div>

              {/* progress bar */}
              {f.status === 'uploading' && (
                <div
                  role="progressbar"
                  aria-valuenow={f.progress}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label={`Uploading ${f.file.name}`}
                  className="h-2 w-24 overflow-hidden rounded-full bg-muted"
                >
                  <div
                    className="h-full bg-primary transition-all"
                    style={{
                      width: `${f.progress}%`,
                    }}
                  />
                </div>
              )}

              {/* status label */}
              <span
                className={`text-xs font-medium ${statusColors[f.status]}`}
                data-testid="file-status"
              >
                {statusLabels[f.status]}
              </span>

              {/* remove button */}
              {f.status !== 'uploading' && (
                <button
                  type="button"
                  data-testid="remove-file"
                  onClick={() => removeFile(f.id)}
                  className="text-xs text-muted-foreground hover:text-foreground"
                >
                  Remove
                </button>
              )}
            </div>
          ))}

          {/* upload all button */}
          {hasPending && (
            <button
              type="button"
              disabled={isUploading}
              onClick={handleUploadAll}
              className="mt-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {isUploading ? 'Uploading...' : 'Upload all'}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
