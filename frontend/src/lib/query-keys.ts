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
  timeline: {
    events: (caseId: string, status?: string) =>
      ['timeline', caseId, 'events', status] as const,
    full: (caseId: string, status?: string) =>
      ['timeline', caseId, 'full', status] as const,
  },
  exports: {
    byCase: (caseId: string) =>
      ['exports', caseId] as const,
    detail: (id: string) =>
      ['exports', 'detail', id] as const,
  },
  transcripts: {
    byAsset: (caseId: string, assetId: string) =>
      ['transcripts', caseId, assetId] as const,
  },
  scenes: {
    byAsset: (caseId: string, assetId: string) =>
      ['scenes', caseId, assetId] as const,
  },
  search: {
    results: (
      caseId: string,
      query: string,
      types?: string[],
    ) =>
      [
        'search',
        caseId,
        query,
        types,
      ] as const,
  },
  duplicates: {
    byCase: (caseId: string) =>
      ['duplicates', caseId] as const,
  },
  users: {
    me: ['users', 'me'] as const,
  },
} as const;
