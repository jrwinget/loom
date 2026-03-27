export interface Organization {
  id: string;
  name: string;
  description: string | null;
  isActive: boolean;
  memberCount: number;
  createdAt: string;
}

export interface OrgMember {
  id: string;
  userId: string;
  userEmail: string;
  role: string;
  joinedAt: string;
}

export interface SharedEvidence {
  id: string;
  sourceCaseId: string;
  targetCaseId: string;
  assetId: string;
  originalFilename: string | null;
  sharedBy: string;
  accessLevel: string;
  expiresAt: string | null;
  createdAt: string;
}
