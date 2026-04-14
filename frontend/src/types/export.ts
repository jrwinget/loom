export interface ExportBundle {
  id: string;
  caseId: string;
  name: string;
  format: string;
  storageKey: string | null;
  sha256Hash: string | null;
  status: 'pending' | 'processing' | 'complete' | 'failed';
  manifest: Record<string, unknown> | null;
  createdBy: string;
  createdAt: string;
}

export interface CreateExportPayload {
  name: string;
  format: 'zip' | 'pdf_report' | 'json_manifest';
  include_originals?: boolean;
  event_ids?: string[];
  asset_ids?: string[];
  date_range_start?: string;
  date_range_end?: string;
}

export interface ExportListResponse {
  items: ExportBundle[];
  total: number;
}
