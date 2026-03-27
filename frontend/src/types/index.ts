export interface User {
  id: string;
  email: string;
  displayName: string;
  role: string;
}

export interface Case {
  id: string;
  name: string;
  description: string;
  status: string;
  assetCount: number;
  eventCount: number;
  createdAt: string;
}

export interface CaseMember {
  id: string;
  userId: string;
  displayName: string;
  email: string;
  role: string;
}

export interface CreateCasePayload {
  name: string;
  description?: string;
}

export interface UpdateCasePayload {
  name?: string;
  description?: string;
  status?: string;
}

export interface ApiError {
  detail: string;
}
