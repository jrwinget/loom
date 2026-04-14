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
  createdAt: string;
  updatedAt: string;
}

export interface AssetListResponse {
  items: Asset[];
  total: number;
}
