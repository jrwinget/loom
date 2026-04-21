import {
  fireEvent,
  render,
  screen,
} from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { TranscriptPanel } from
  '@/components/review/transcript-panel';
import type { TranscriptSegment } from
  '@/types/transcript';

function makeSegment(
  overrides: Partial<TranscriptSegment> = {},
): TranscriptSegment {
  return {
    id: 'seg-1',
    assetId: 'asset-1',
    speakerLabel: 'Speaker A',
    startTime: 0,
    endTime: 5,
    text: 'Hello world',
    confidence: 0.95,
    language: 'en',
    ...overrides,
  };
}

describe('TranscriptPanel', () => {
  const segments: TranscriptSegment[] = [
    makeSegment({
      id: 'seg-1',
      speakerLabel: 'Speaker A',
      startTime: 0,
      endTime: 5,
      text: 'First segment',
    }),
    makeSegment({
      id: 'seg-2',
      speakerLabel: 'Speaker B',
      startTime: 5,
      endTime: 10,
      text: 'Second segment',
    }),
    makeSegment({
      id: 'seg-3',
      speakerLabel: 'Speaker A',
      startTime: 10,
      endTime: 15,
      text: 'Third segment',
    }),
  ];

  it('renders all segments', () => {
    render(
      <TranscriptPanel
        segments={segments}
        currentTime={0}
        onSeek={vi.fn()}
      />,
    );

    expect(
      screen.getByText('First segment'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Second segment'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Third segment'),
    ).toBeInTheDocument();
  });

  it('highlights current segment', () => {
    render(
      <TranscriptPanel
        segments={segments}
        currentTime={7}
        onSeek={vi.fn()}
      />,
    );

    const seg2 = screen.getByTestId('segment-seg-2');
    expect(seg2).toHaveAttribute('data-active', 'true');

    const seg1 = screen.getByTestId('segment-seg-1');
    expect(seg1).toHaveAttribute('data-active', 'false');
  });

  it('calls onSeek when segment is clicked', () => {
    const onSeek = vi.fn();
    render(
      <TranscriptPanel
        segments={segments}
        currentTime={0}
        onSeek={onSeek}
      />,
    );

    fireEvent.click(
      screen.getByTestId('segment-seg-2'),
    );
    expect(onSeek).toHaveBeenCalledWith(5);
  });

  it('filters by speaker', () => {
    render(
      <TranscriptPanel
        segments={segments}
        currentTime={0}
        onSeek={vi.fn()}
      />,
    );

    const filter = screen.getByTestId('speaker-filter');
    fireEvent.change(filter, {
      target: { value: 'Speaker B' },
    });

    // only speaker B segment visible
    expect(
      screen.getByText('Second segment'),
    ).toBeInTheDocument();
    expect(
      screen.queryByText('First segment'),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText('Third segment'),
    ).not.toBeInTheDocument();
  });

  it('shows empty state when no segments', () => {
    render(
      <TranscriptPanel
        segments={[]}
        currentTime={0}
        onSeek={vi.fn()}
      />,
    );

    expect(
      screen.getByText(
        'No transcript segments available',
      ),
    ).toBeInTheDocument();
  });
});
