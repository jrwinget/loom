import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { createElement } from 'react';
import { describe, expect, it, vi } from 'vitest';
import {
  useTimelineEvents,
  useTimeline,
  useCreateEvent,
  useUpdateEvent,
  useLinkEvidence,
} from '@/hooks/use-timeline';
import type { TimelineEvent, EvidenceLink } from '@/types/timeline';

const mockEvent: TimelineEvent = {
  id: 'event-1',
  caseId: 'case-1',
  title: 'Protest at City Hall',
  description: 'Peaceful demonstration',
  eventTimeStart: '2026-01-15T10:00:00Z',
  eventTimeEnd: null,
  timePrecision: 'exact',
  locationDescription: 'City Hall steps',
  locationLat: 45.5,
  locationLon: -122.6,
  locationConfidence: 'gps',
  status: 'draft',
  createdBy: 'user-1',
  createdAt: '2026-01-15T10:00:00Z',
  updatedAt: '2026-01-15T10:00:00Z',
  evidenceCount: 3,
  hasContradictions: false,
};

const mockLink: EvidenceLink = {
  id: 'link-1',
  eventId: 'event-1',
  assetId: 'asset-1',
  annotationId: null,
  derivativeId: null,
  clipStart: null,
  clipEnd: null,
  relationship: 'supports',
  notes: null,
  linkedBy: 'user-1',
  linkedAt: '2026-01-15T10:00:00Z',
};

vi.mock('@/lib/api-client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('@/stores/toast-store', () => ({
  useToastStore: {
    getState: () => ({ addToast: vi.fn() }),
  },
}));

function createWrapper(): ({ children }: { children: React.ReactNode }) => React.ReactElement {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
    },
  });
  return ({ children }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

describe('useTimelineEvents', () => {
  it('fetches events for a case', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      items: [mockEvent],
      total: 1,
    });

    const { result } = renderHook(
      () => useTimelineEvents('case-1'),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.items).toHaveLength(1);
    expect(result.current.data?.items[0]?.title).toBe(
      'Protest at City Hall',
    );
  });

  it('is disabled when caseId is empty', () => {
    const { result } = renderHook(
      () => useTimelineEvents(''),
      { wrapper: createWrapper() },
    );

    expect(result.current.fetchStatus).toBe('idle');
  });

  it('supports status filter', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      items: [],
      total: 0,
    });

    const { result } = renderHook(
      () => useTimelineEvents('case-1', 'draft'),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(vi.mocked(apiClient.get)).toHaveBeenCalledWith(
      '/cases/case-1/events?status=draft',
    );
  });
});

describe('useTimeline', () => {
  it('fetches full timeline', async () => {
    const { apiClient } = await import('@/lib/api-client');
    vi.mocked(apiClient.get).mockResolvedValueOnce({
      events: [{ ...mockEvent, evidence: [mockLink] }],
    });

    const { result } = renderHook(
      () => useTimeline('case-1'),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.events).toHaveLength(1);
  });

  it('is disabled when caseId is empty', () => {
    const { result } = renderHook(
      () => useTimeline(''),
      { wrapper: createWrapper() },
    );

    expect(result.current.fetchStatus).toBe('idle');
  });
});

describe('useCreateEvent', () => {
  it('exposes mutate function', () => {
    const { result } = renderHook(
      () => useCreateEvent(),
      { wrapper: createWrapper() },
    );

    expect(result.current.mutate).toBeDefined();
    expect(result.current.mutateAsync).toBeDefined();
  });
});

describe('useUpdateEvent', () => {
  it('exposes mutate function', () => {
    const { result } = renderHook(
      () => useUpdateEvent(),
      { wrapper: createWrapper() },
    );

    expect(result.current.mutate).toBeDefined();
  });
});

describe('useLinkEvidence', () => {
  it('exposes mutate function', () => {
    const { result } = renderHook(
      () => useLinkEvidence(),
      { wrapper: createWrapper() },
    );

    expect(result.current.mutate).toBeDefined();
  });
});
