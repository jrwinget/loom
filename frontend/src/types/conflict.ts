export interface EvidenceDetail {
  id: string;
  assetId: string | null;
  originalFilename: string | null;
  annotationId: string | null;
  clipStart: number | null;
  clipEnd: number | null;
  relationship: string;
  notes: string | null;
}

export interface ConflictResolution {
  id: string;
  eventId: string;
  resolutionType: string;
  notes: string | null;
  resolvedBy: string;
  createdAt: string;
}

export interface ConflictDetail {
  eventId: string;
  eventTitle: string;
  supporting: EvidenceDetail[];
  contradicting: EvidenceDetail[];
  resolutions: ConflictResolution[];
}

export interface ConflictListItem {
  eventId: string;
  eventTitle: string;
  supportingCount: number;
  contradictingCount: number;
  resolutionCount: number;
  isResolved: boolean;
}

export interface ConflictListResponse {
  items: ConflictListItem[];
  total: number;
}

export interface CreateResolutionPayload {
  resolutionType: string;
  notes?: string;
}
