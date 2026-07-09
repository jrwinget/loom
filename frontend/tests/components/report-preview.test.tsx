/// <reference types="@testing-library/jest-dom" />
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { axe } from 'jest-axe';
import { createElement } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api-client', () => ({
  apiClient: { get: vi.fn() },
}));

import { apiClient } from '@/lib/api-client';
import { ReportPreview } from '@/components/export/report-preview';
import type { EvidenceLink, TimelineEventDetail } from '@/types/timeline';

const mockedGet = vi.mocked(apiClient.get);

function makeEvidence(relationship: string): EvidenceLink {
  return {
    id: `ev-${relationship}`,
    eventId: 'event-1',
    assetId: 'asset-1',
    annotationId: null,
    derivativeId: null,
    clipStart: null,
    clipEnd: null,
    relationship,
    notes: null,
    linkedBy: 'user-1',
    linkedAt: '2026-01-01T00:00:00Z',
  };
}

function makeEvent(): TimelineEventDetail {
  return {
    id: 'event-1',
    caseId: 'case-1',
    title: 'Doorway entry',
    description: null,
    eventTimeStart: '2026-01-01T00:00:00Z',
    eventTimeEnd: null,
    timePrecision: 'minute',
    locationDescription: null,
    locationLat: null,
    locationLon: null,
    locationConfidence: 'high',
    status: 'accepted',
    createdBy: 'user-1',
    createdAt: '2026-01-01T00:00:00Z',
    updatedAt: '2026-01-01T00:00:00Z',
    evidenceCount: 3,
    hasContradictions: true,
    evidence: [
      makeEvidence('supports'),
      makeEvidence('supports'),
      makeEvidence('contradicts'),
    ],
  };
}

function wrapper(): React.FC<{ children: React.ReactNode }> {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }) =>
    createElement(QueryClientProvider, { client: qc }, children);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('ReportPreview', () => {
  it('summarizes supporting and contradicting evidence per event', async () => {
    mockedGet.mockResolvedValue({ events: [makeEvent()] });

    render(<ReportPreview caseId="case-1" caseName="Operation Nightingale" />, {
      wrapper: wrapper(),
    });

    await waitFor(() =>
      expect(screen.getByTestId('preview-event-event-1')).toBeInTheDocument(),
    );
    expect(
      screen.getByText('2 supporting, 1 contradicting'),
    ).toBeInTheDocument();
  });

  it('shows an empty message when the timeline has no events', async () => {
    mockedGet.mockResolvedValue({ events: [] });

    render(<ReportPreview caseId="case-1" caseName="Case" />, {
      wrapper: wrapper(),
    });

    await waitFor(() =>
      expect(
        screen.getByText('No events to include in the report.'),
      ).toBeInTheDocument(),
    );
  });

  it('has no accessibility violations', async () => {
    mockedGet.mockResolvedValue({ events: [makeEvent()] });

    const { container } = render(
      <ReportPreview caseId="case-1" caseName="Case" />,
      { wrapper: wrapper() },
    );

    await waitFor(() =>
      expect(screen.getByTestId('preview-event-event-1')).toBeInTheDocument(),
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
