export type CorrelationStatus = 'pending' | 'accepted' | 'rejected';

export interface CorrelationCandidateMember {
  id: string;
  asset_id: string;
  original_filename: string | null;
  capture_time: string | null;
}

export interface CorrelationReasoning {
  [signal: string]:
    | {
        score: number | null;
        notes?: string | null;
      }
    | unknown;
}

export interface CorrelationCandidate {
  id: string;
  case_id: string;
  start_utc: string;
  end_utc: string;
  confidence: number;
  reasoning: CorrelationReasoning;
  status: CorrelationStatus;
  decided_by: string | null;
  decided_at: string | null;
  members: CorrelationCandidateMember[];
  created_at: string;
}

export interface CorrelationCandidateListResponse {
  candidates: CorrelationCandidate[];
  total: number;
}

export interface CorrelationDecisionPayload {
  status: Exclude<CorrelationStatus, 'pending'>;
}
