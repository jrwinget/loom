export interface ExportContents {
  included: Record<string, number>;
  excluded: Record<string, string>;
}

export interface ExportBundle {
  id: string;
  caseId: string;
  name: string;
  format: string;
  storageKey: string | null;
  sha256Hash: string | null;
  downloadUrl: string | null;
  status: 'pending' | 'processing' | 'complete' | 'failed';
  manifest: Record<string, unknown> | null;
  // the request as submitted; keys are verbatim snake_case (opaque
  // to the api-client transform, like manifest)
  options: Record<string, unknown> | null;
  createdBy: string;
  createdAt: string;
}

export interface CreateExportPayload {
  name: string;
  format:
    'zip' | 'pdf_report' | 'json_manifest' | 'court_bundle' | 'portable_bundle';
  include_originals?: boolean;
  include_analysis?: boolean;
  event_ids?: string[];
  asset_ids?: string[];
  date_range_start?: string;
  date_range_end?: string;
  // pdf-report composition controls (report builder)
  include_evidence?: boolean;
  include_contradictions?: boolean;
  include_custody?: boolean;
  executive_summary?: string;
}

export interface ExportListResponse {
  items: ExportBundle[];
  total: number;
}
