// storage domain types. ui layer uses camelCase; wire types
// mirror the api response shape (already camelCase after the
// api-client key conversion) and are suffixed with *Wire and
// mapped to domain shapes at the hook boundary.

export type StorageAdvisory = 'proceed' | 'warning' | 'blocked';

export type RelocationStatus = 'running' | 'completed' | 'failed';

export interface StorageUsage {
  dataDir: string;
  freeBytes: number;
  totalBytes: number;
  originalsBytes: number;
  derivativesBytes: number;
  dbBytes: number;
  logsBytes: number;
  assetCount: number;
  onSystemDrive: boolean;
}

export interface StorageUsageWire {
  dataDir: string;
  freeBytes: number;
  totalBytes: number;
  originalsBytes: number;
  derivativesBytes: number;
  dbBytes: number;
  logsBytes: number;
  assetCount: number;
  onSystemDrive: boolean;
}

export interface StorageCheckRequest {
  path: string;
  estimatedBatchSize: number;
}

export interface StorageCheckResult {
  writable: boolean;
  writableReason: string | null;
  freeBytes: number;
  totalBytes: number;
  onSystemDrive: boolean;
  advisory: StorageAdvisory;
  advisoryReason: string | null;
}

export interface StorageCheckResultWire {
  writable: boolean;
  writableReason: string | null;
  freeBytes: number;
  totalBytes: number;
  onSystemDrive: boolean;
  advisory: StorageAdvisory;
  advisoryReason: string | null;
}

export interface RelocateRequest {
  targetPath: string;
}

export interface RelocateAcceptedResponseWire {
  jobId: string;
}

export interface RelocationJob {
  jobId: string;
  status: RelocationStatus;
  assetsCopied: number;
  assetsTotal: number;
  bytesCopied: number;
  bytesTotal: number;
  error: string | null;
  startedAt: string | null;
  completedAt: string | null;
}

export interface RelocationJobWire {
  jobId: string;
  status: RelocationStatus;
  assetsCopied: number;
  assetsTotal: number;
  bytesCopied: number;
  bytesTotal: number;
  error: string | null;
  startedAt: string | null;
  completedAt: string | null;
}
