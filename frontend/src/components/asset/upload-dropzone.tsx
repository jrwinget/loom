import { useCallback, useMemo, useRef, useState } from 'react';
import * as Tabs from '@radix-ui/react-tabs';
import { useUpload } from '@/hooks/use-upload';
import type { UploadFile } from '@/hooks/use-upload';
import { StorageAdvisory } from '@/components/asset/storage-advisory';
import { UrlIngestForm } from '@/components/asset/url-ingest-form';

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

  // pass only unfinished uploads to the advisory so the banner
  // disappears as soon as everything has landed.
  const advisoryFiles = useMemo(
    () =>
      files
        .filter((f) => f.status === 'pending' || f.status === 'uploading')
        .map((f) => f.file),
    [files],
  );

  return (
    <div data-testid="upload-dropzone">
      <Tabs.Root defaultValue="files" data-testid="upload-tabs">
        <Tabs.List className="mb-4 flex gap-1 border-b border-border">
          <Tabs.Trigger
            value="files"
            data-testid="tab-files"
            className="border-b-2 border-transparent px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground data-[state=active]:border-primary data-[state=active]:text-foreground"
          >
            Files
          </Tabs.Trigger>
          <Tabs.Trigger
            value="url"
            data-testid="tab-url"
            className="border-b-2 border-transparent px-4 py-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground data-[state=active]:border-primary data-[state=active]:text-foreground"
          >
            URL
          </Tabs.Trigger>
        </Tabs.List>

        <Tabs.Content value="files">
          <StorageAdvisory selectedFiles={advisoryFiles} />
          {/* drop area */}
          <div
            data-testid="drop-area"
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition-colors ${
              dragOver ? 'border-primary bg-primary/5' : 'border-border bg-card'
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
                  className="flex items-center gap-3 rounded-md border border-border bg-card p-3"
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
        </Tabs.Content>

        <Tabs.Content value="url">
          <UrlIngestForm caseId={caseId} />
        </Tabs.Content>
      </Tabs.Root>
    </div>
  );
}
