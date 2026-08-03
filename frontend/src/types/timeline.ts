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
  status?: EventStatus;
}

export interface UpdateEventPayload {
  title?: string;
  description?: string;
  event_time_start?: string;
  event_time_end?: string;
  time_precision?: string;
  status?: EventStatus;
}

export interface LinkEvidencePayload {
  asset_id?: string;
  annotation_id?: string;
  derivative_id?: string;
  clip_start?: number;
  clip_end?: number;
  relationship: EvidenceRelationship;
  notes?: string;
}

export type EventStatus = 'draft' | 'confirmed' | 'disputed';

export const EVENT_STATUSES: readonly EventStatus[] = [
  'draft',
  'confirmed',
  'disputed',
];

export type EvidenceRelationship = 'supports' | 'contradicts' | 'context';

export const EVIDENCE_RELATIONSHIPS: readonly EvidenceRelationship[] = [
  'supports',
  'contradicts',
  'context',
];

export type ZoomLevel = 'hours' | 'days' | 'weeks';
