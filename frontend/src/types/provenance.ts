export interface ProvenanceRecord {
  id: string;
  assetId: string | null;
  exportId: string | null;
  manifestData: Record<string, unknown>;
  claimGenerator: string;
  actions: Array<Record<string, unknown>>;
  createdAt: string;
}

export interface ProvenanceListResponse {
  items: ProvenanceRecord[];
  total: number;
}
