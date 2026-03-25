export const queryKeys = {
  cases: {
    all: ['cases'] as const,
    detail: (id: string) => ['cases', id] as const,
    members: (caseId: string) =>
      ['cases', caseId, 'members'] as const,
  },
  assets: {
    byCase: (caseId: string) => ['assets', caseId] as const,
    detail: (id: string) => ['assets', 'detail', id] as const,
  },
  annotations: {
    byAsset: (assetId: string) =>
      ['annotations', assetId] as const,
    detail: (id: string) =>
      ['annotations', 'detail', id] as const,
  },
  users: {
    me: ['users', 'me'] as const,
  },
} as const;
