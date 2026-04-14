export const queryKeys = {
  cases: {
    all: ['cases'] as const,
    detail: (id: string) => ['cases', id] as const,
    members: (caseId: string) => ['cases', caseId, 'members'] as const,
  },
  assets: {
    byCase: (caseId: string) => ['assets', caseId] as const,
    detail: (id: string) => ['assets', 'detail', id] as const,
  },
  annotations: {
    byAsset: (assetId: string) => ['annotations', assetId] as const,
    detail: (id: string) => ['annotations', 'detail', id] as const,
  },
  timeline: {
    events: (caseId: string, status?: string) =>
      ['timeline', caseId, 'events', status] as const,
    full: (caseId: string, status?: string) =>
      ['timeline', caseId, 'full', status] as const,
  },
  exports: {
    byCase: (caseId: string) => ['exports', caseId] as const,
    detail: (id: string) => ['exports', 'detail', id] as const,
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
    results: (caseId: string, query: string, types?: string[]) =>
      ['search', caseId, query, types] as const,
  },
  conflicts: {
    byCase: (caseId: string, resolved?: boolean) =>
      ['conflicts', caseId, resolved] as const,
    detail: (caseId: string, eventId: string) =>
      ['conflicts', caseId, eventId] as const,
  },
  duplicates: {
    byCase: (caseId: string) => ['duplicates', caseId] as const,
  },
  clusters: {
    byCase: (caseId: string, status?: string) =>
      ['clusters', caseId, status] as const,
    detail: (caseId: string, clusterId: string) =>
      ['clusters', caseId, clusterId] as const,
  },
  geo: {
    assets: (caseId: string, timeStart?: string, timeEnd?: string) =>
      ['geo', caseId, 'assets', timeStart, timeEnd] as const,
    events: (caseId: string, timeStart?: string, timeEnd?: string) =>
      ['geo', caseId, 'events', timeStart, timeEnd] as const,
    bounds: (caseId: string) => ['geo', caseId, 'bounds'] as const,
  },
  organizations: {
    all: ['organizations'] as const,
    detail: (id: string) => ['organizations', id] as const,
    members: (orgId: string) => ['organizations', orgId, 'members'] as const,
  },
  sharedEvidence: {
    incoming: (caseId: string) =>
      ['shared-evidence', caseId, 'incoming'] as const,
    outgoing: (caseId: string) =>
      ['shared-evidence', caseId, 'outgoing'] as const,
  },
  provenance: {
    byAsset: (caseId: string, assetId: string) =>
      ['provenance', caseId, 'asset', assetId] as const,
    byExport: (caseId: string, exportId: string) =>
      ['provenance', caseId, 'export', exportId] as const,
  },
  plugins: {
    all: ['plugins'] as const,
    detail: (id: string) => ['plugins', id] as const,
    webhooks: (pluginId: string) => ['plugins', pluginId, 'webhooks'] as const,
    deliveries: (pluginId: string, webhookId: string) =>
      ['plugins', pluginId, 'webhooks', webhookId, 'deliveries'] as const,
  },
  audit: {
    byCase: (caseId: string) => ['audit', caseId] as const,
  },
  custody: {
    byAsset: (caseId: string, assetId: string) =>
      ['custody', caseId, assetId] as const,
  },
  users: {
    me: ['users', 'me'] as const,
  },
  mfa: {
    status: ['mfa', 'status'] as const,
  },
} as const;
