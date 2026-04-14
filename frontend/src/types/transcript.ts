export interface TranscriptSegment {
  id: string;
  assetId: string;
  speakerLabel: string | null;
  startTime: number;
  endTime: number;
  text: string;
  confidence: number | null;
  language: string | null;
}

export interface TranscriptResponse {
  segments: TranscriptSegment[];
  totalDuration: number;
  language: string | null;
  speakerCount: number;
}

export interface SceneInfo {
  id: string;
  assetId: string;
  sceneNumber: number;
  startTime: number;
  endTime: number;
  thumbnailUrl: string | null;
  duration: number;
}

export interface OcrRegion {
  id: string;
  assetId: string;
  frameNumber: number | null;
  timestamp: number | null;
  text: string;
  confidence: number | null;
}

export interface SearchResult {
  type: string;
  id: string;
  text: string;
  assetId: string | null;
  relevanceScore: number;
  metadata: Record<string, unknown>;
}

export interface SearchResponse {
  results: SearchResult[];
  total: number;
  facets: Record<string, number>;
}

export interface DuplicateCluster {
  id: string;
  caseId: string;
  status: string;
  members: DuplicateClusterMember[];
  createdAt: string;
}

export interface DuplicateClusterMember {
  id: string;
  assetId: string;
  originalFilename: string;
  distance: number | null;
  isPrimary: boolean;
}
