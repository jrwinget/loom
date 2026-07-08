export type CorrelationStatus = 'pending' | 'accepted' | 'rejected';

export interface CorrelationCandidateMember {
  id: string;
  assetId: string;
  originalFilename: string | null;
  captureTime: string | null;
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
  caseId: string;
  startUtc: string;
  endUtc: string;
  confidence: number;
  reasoning: CorrelationReasoning;
  status: CorrelationStatus;
  decidedBy: string | null;
  decidedAt: string | null;
  members: CorrelationCandidateMember[];
  createdAt: string;
}

export interface CorrelationCandidateListResponse {
  candidates: CorrelationCandidate[];
  total: number;
}

export interface CorrelationDecisionPayload {
  status: Exclude<CorrelationStatus, 'pending'>;
}
