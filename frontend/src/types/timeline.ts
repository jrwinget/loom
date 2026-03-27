export interface TimelineEvent {
  id: string;
  caseId: string;
  title: string;
  description: string | null;
  eventTimeStart: string;
  eventTimeEnd: string | null;
  timePrecision: string;
  locationDescription: string | null;
  locationLat: number | null;
  locationLon: number | null;
  locationConfidence: string;
  status: string;
  createdBy: string;
  createdAt: string;
  updatedAt: string;
  evidenceCount: number;
  hasContradictions: boolean;
}

export interface EvidenceLink {
  id: string;
  eventId: string;
  assetId: string | null;
  annotationId: string | null;
  derivativeId: string | null;
  clipStart: number | null;
  clipEnd: number | null;
  relationship: string;
  notes: string | null;
  linkedBy: string;
  linkedAt: string;
}

export interface TimelineEventDetail extends TimelineEvent {
  evidence: EvidenceLink[];
}

export interface CreateEventPayload {
  title: string;
  description?: string;
  event_time_start: string;
  event_time_end?: string;
  time_precision?: string;
  location_description?: string;
  location_lat?: number;
  location_lon?: number;
  location_confidence?: string;
  status?: string;
}

export interface UpdateEventPayload {
  title?: string;
  description?: string;
  event_time_start?: string;
  event_time_end?: string;
  time_precision?: string;
  status?: string;
}

export interface LinkEvidencePayload {
  asset_id?: string;
  annotation_id?: string;
  derivative_id?: string;
  clip_start?: number;
  clip_end?: number;
  relationship: string;
  notes?: string;
}

export type EventStatus = 'draft' | 'proposed' | 'accepted' | 'rejected';

export type ZoomLevel = 'hours' | 'days' | 'weeks';
