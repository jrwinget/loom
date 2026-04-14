export interface ClusterItem {
  id: string;
  assetId: string;
  originalFilename: string;
  contentType: string;
  contentId: string;
  absoluteTimeStart: string;
  absoluteTimeEnd: string | null;
  textPreview: string | null;
}

export interface EventCluster {
  id: string;
  caseId: string;
  status: 'proposed' | 'accepted' | 'rejected';
  proposedTitle: string;
  proposedDescription: string | null;
  timeWindowStart: string;
  timeWindowEnd: string;
  eventId: string | null;
  items: ClusterItem[];
}

export interface ClusterListResponse {
  items: EventCluster[];
  total: number;
}

export interface ProposePayload {
  window_seconds: number;
}

export interface AcceptPayload {
  title?: string;
  description?: string;
}
