import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import {
  TimelineEventCard,
} from '@/components/timeline/timeline-event';
import type { TimelineEvent } from '@/types/timeline';

const mockEvent: TimelineEvent = {
  id: 'evt-1',
  caseId: 'case-1',
  title: 'Protest at City Hall',
  description: 'Large gathering observed',
  eventTimeStart: '2026-03-15T14:00:00Z',
  eventTimeEnd: '2026-03-15T16:00:00Z',
  timePrecision: 'minute',
  locationDescription: '100 Main St',
  locationLat: 40.7128,
  locationLon: -74.006,
  locationConfidence: 'high',
  status: 'proposed',
  createdBy: 'user-1',
  createdAt: '2026-03-15T18:00:00Z',
  updatedAt: '2026-03-15T18:00:00Z',
  evidenceCount: 3,
  hasContradictions: false,
};

function renderCard(
  overrides: Partial<TimelineEvent> = {},
  selected = false,
  onClick = vi.fn(),
  onConflictClick?: (event: TimelineEvent) => void,
): { onClick: ReturnType<typeof vi.fn> } {
  render(
    <TimelineEventCard
      event={{ ...mockEvent, ...overrides }}
      selected={selected}
      onClick={onClick}
      onConflictClick={onConflictClick}
    />,
  );
  return { onClick };
}

describe('TimelineEventCard', () => {
  it('renders event title', () => {
    renderCard();
    expect(
      screen.getByText('Protest at City Hall'),
    ).toBeInTheDocument();
  });

  it('renders timestamp range', () => {
    renderCard();
    // both start and end formatted
    const text = screen
      .getByTestId('timeline-event-evt-1')
      .textContent;
    expect(text).toContain('Mar');
    expect(text).toContain('2026');
  });

  it('renders single timestamp when no end time', () => {
    renderCard({ eventTimeEnd: null });
    const card = screen.getByTestId('timeline-event-evt-1');
    // should not contain " - " separator for range
    const timeTexts = card.querySelectorAll(
      '.text-muted-foreground',
    );
    expect(timeTexts.length).toBeGreaterThan(0);
  });

  it('shows evidence count badge', () => {
    renderCard({ evidenceCount: 3 });
    expect(
      screen.getByText('3 evidence links'),
    ).toBeInTheDocument();
  });

  it('shows singular evidence link text for count of 1', () => {
    renderCard({ evidenceCount: 1 });
    expect(
      screen.getByText('1 evidence link'),
    ).toBeInTheDocument();
  });

  it('shows status badge', () => {
    renderCard({ status: 'proposed' });
    const badge = screen.getByTestId('event-status-badge');
    expect(badge).toHaveTextContent('proposed');
    expect(badge.className).toContain('blue');
  });

  it('shows accepted status with green styling', () => {
    renderCard({ status: 'accepted' });
    const badge = screen.getByTestId('event-status-badge');
    expect(badge).toHaveTextContent('accepted');
    expect(badge.className).toContain('green');
  });

  it('handles click and passes event', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    renderCard({}, false, onClick);

    await user.click(
      screen.getByTestId('timeline-event-evt-1'),
    );
    expect(onClick).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'evt-1' }),
    );
  });

  it('has visual indication when selected', () => {
    renderCard({}, true);
    const card = screen.getByTestId('timeline-event-evt-1');
    expect(card.className).toContain('border-primary');
  });

  it('has default styling when not selected', () => {
    renderCard({}, false);
    const card = screen.getByTestId('timeline-event-evt-1');
    expect(card.className).toContain('bg-card');
    expect(card.className).not.toContain('border-primary');
  });

  it('shows location description when present', () => {
    renderCard({ locationDescription: '100 Main St' });
    expect(
      screen.getByText(/100 Main St/),
    ).toBeInTheDocument();
  });

  it('hides location when null', () => {
    renderCard({ locationDescription: null });
    expect(
      screen.queryByText(/100 Main St/),
    ).not.toBeInTheDocument();
  });

  it('shows contradiction indicator when present', () => {
    renderCard({ hasContradictions: true });
    expect(
      screen.getByTestId('contradiction-indicator'),
    ).toBeInTheDocument();
  });

  it('hides contradiction indicator when absent', () => {
    renderCard({ hasContradictions: false });
    expect(
      screen.queryByTestId('contradiction-indicator'),
    ).not.toBeInTheDocument();
  });

  it('calls onConflictClick when contradiction clicked', async () => {
    const user = userEvent.setup();
    const onConflictClick = vi.fn();
    const onClick = vi.fn();

    renderCard(
      { hasContradictions: true },
      false,
      onClick,
      onConflictClick,
    );

    await user.click(
      screen.getByTestId('contradiction-indicator'),
    );

    expect(onConflictClick).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'evt-1' }),
    );
    // should not bubble to card onClick
    expect(onClick).not.toHaveBeenCalled();
  });

  it('shows time precision label', () => {
    renderCard({ timePrecision: 'minute' });
    expect(screen.getByText('minute')).toBeInTheDocument();
  });
});
