import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TimelineCanvas } from
  '@/components/timeline/timeline-canvas';
import type { TimelineEvent } from
  '@/types/timeline';

function makeEvent(
  overrides: Partial<TimelineEvent> = {},
): TimelineEvent {
  return {
    id: 'event-1',
    caseId: 'case-1',
    title: 'Test Event',
    description: null,
    eventTimeStart: '2026-01-15T10:00:00Z',
    eventTimeEnd: null,
    timePrecision: 'approximate',
    locationDescription: null,
    locationLat: null,
    locationLon: null,
    locationConfidence: 'unknown',
    status: 'draft',
    createdBy: 'user-1',
    createdAt: '2026-01-15T10:00:00Z',
    updatedAt: '2026-01-15T10:00:00Z',
    evidenceCount: 0,
    hasContradictions: false,
    ...overrides,
  };
}

const onSelect = vi.fn();

describe('TimelineCanvas', () => {
  it('renders events', () => {
    const events = [
      makeEvent({ id: 'e1', title: 'First' }),
      makeEvent({ id: 'e2', title: 'Second' }),
    ];
    render(
      <TimelineCanvas
        events={events}
        selectedEventId={null}
        onSelectEvent={onSelect}
      />,
    );
    expect(
      screen.getByText('First'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Second'),
    ).toBeInTheDocument();
  });

  it('applies status color coding', () => {
    const events = [
      makeEvent({
        id: 'e1',
        status: 'draft',
      }),
      makeEvent({
        id: 'e2',
        status: 'proposed',
      }),
      makeEvent({
        id: 'e3',
        status: 'accepted',
      }),
      makeEvent({
        id: 'e4',
        status: 'rejected',
      }),
    ];
    render(
      <TimelineCanvas
        events={events}
        selectedEventId={null}
        onSelectEvent={onSelect}
      />,
    );
    const badges = screen.getAllByTestId(
      'event-status-badge',
    );
    expect(badges).toHaveLength(4);
    expect(badges[0].className).toContain('gray');
    expect(badges[1].className).toContain('blue');
    expect(badges[2].className).toContain('green');
    expect(badges[3].className).toContain('red');
  });

  it('shows empty state when no events', () => {
    render(
      <TimelineCanvas
        events={[]}
        selectedEventId={null}
        onSelectEvent={onSelect}
      />,
    );
    expect(
      screen.getByText(
        'No events on this timeline yet',
      ),
    ).toBeInTheDocument();
  });

  it('shows loading skeleton', () => {
    render(
      <TimelineCanvas
        events={[]}
        selectedEventId={null}
        onSelectEvent={onSelect}
        loading
      />,
    );
    const skeletons = screen.getAllByTestId(
      'skeleton-event',
    );
    expect(skeletons.length).toBeGreaterThan(0);
  });

  it('shows contradiction indicator', () => {
    const events = [
      makeEvent({
        id: 'e1',
        hasContradictions: true,
      }),
    ];
    render(
      <TimelineCanvas
        events={events}
        selectedEventId={null}
        onSelectEvent={onSelect}
      />,
    );
    expect(
      screen.getByTestId(
        'contradiction-indicator',
      ),
    ).toBeInTheDocument();
  });
});
