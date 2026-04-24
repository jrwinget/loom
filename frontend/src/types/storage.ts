// storage domain types. ui layer uses camelCase; wire types
// (snake_case) are suffixed with *Wire and converted at the
// hook boundary.

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
  data_dir: string;
  free_bytes: number;
  total_bytes: number;
  originals_bytes: number;
  derivatives_bytes: number;
  db_bytes: number;
  logs_bytes: number;
  asset_count: number;
  on_system_drive: boolean;
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
  writable_reason: string | null;
  free_bytes: number;
  total_bytes: number;
  on_system_drive: boolean;
  advisory: StorageAdvisory;
  advisory_reason: string | null;
}

export interface RelocateRequest {
  targetPath: string;
}

export interface RelocateAcceptedResponseWire {
  job_id: string;
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
  job_id: string;
  status: RelocationStatus;
  assets_copied: number;
  assets_total: number;
  bytes_copied: number;
  bytes_total: number;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
}
