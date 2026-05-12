/// <reference types="@testing-library/jest-dom" />
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { TimelineEventCard } from '@/components/timeline/timeline-event';
import type { TimelineEvent } from '@/types/timeline';

function makeEvent(overrides: Partial<TimelineEvent> = {}): TimelineEvent {
  return {
    id: 'evt-1',
    caseId: 'case-1',
    title: 'Test event',
    description: null,
    eventTimeStart: '2026-05-12T10:00:00Z',
    eventTimeEnd: null,
    timePrecision: 'second',
    locationDescription: null,
    locationLat: null,
    locationLon: null,
    locationConfidence: 'low',
    status: 'draft',
    createdBy: 'user-1',
    createdAt: '2026-05-12T09:00:00Z',
    updatedAt: '2026-05-12T09:00:00Z',
    evidenceCount: 0,
    hasContradictions: false,
    ...overrides,
  };
}

describe('TimelineEventCard', () => {
  it('renders the probable-match badge when isProbableMatch is true', () => {
    render(
      <TimelineEventCard
        event={makeEvent()}
        selected={false}
        onClick={() => {}}
        isProbableMatch
      />,
    );
    expect(screen.getByTestId('probable-match-badge')).toHaveTextContent(
      /probable match/i,
    );
  });

  it('omits the probable-match badge by default', () => {
    render(
      <TimelineEventCard
        event={makeEvent()}
        selected={false}
        onClick={() => {}}
      />,
    );
    expect(
      screen.queryByTestId('probable-match-badge'),
    ).not.toBeInTheDocument();
  });
});
