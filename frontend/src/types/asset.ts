export type MediaType = 'video' | 'image' | 'audio' | 'document' | 'other';
export type UploadStatus = 'pending' | 'uploading' | 'complete' | 'failed';
export type ProcessingStatus = 'pending' | 'processing' | 'complete' | 'failed';

export interface Asset {
  id: string;
  caseId: string;
  originalFilename: string;
  storageKey: string;
  mediaType: MediaType;
  mimeType: string;
  fileSizeBytes: number;
  sha256Hash: string;
  uploadStatus: UploadStatus;
  processingStatus: ProcessingStatus;
  captureTime: string | null;
  // seconds to add to a reported timestamp to recover actual time.
  // null = no user anchor recorded yet.
  clockOffsetSeconds: number | null;
  // 0.0-1.0 confidence in the recorded clock offset or in the
  // automatic agreement of exif/container/filename time sources.
  // null = too few sources to assess.
  clockConfidence: number | null;
  createdAt: string;
  updatedAt: string;
}

export interface AssetListResponse {
  items: Asset[];
  total: number;
}
