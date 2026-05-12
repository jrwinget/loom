/// <reference types="@testing-library/jest-dom" />
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { TimelineControls } from '@/components/timeline/timeline-controls';

function renderControls(
  overrides: {
    confidenceThreshold?: number;
    onConfidenceThresholdChange?: (value: number) => void;
  } = {},
) {
  const baseProps = {
    onAddEvent: vi.fn(),
    statusFilter: 'all' as const,
    onStatusFilterChange: vi.fn(),
    zoomLevel: 'days' as const,
    onZoomChange: vi.fn(),
    ...overrides,
  };
  return render(<TimelineControls {...baseProps} />);
}

describe('TimelineControls correlation threshold', () => {
  it('hides the threshold control when no callback is provided', () => {
    renderControls();
    expect(
      screen.queryByTestId('correlation-threshold'),
    ).not.toBeInTheDocument();
  });

  it('renders the threshold slider when value and callback are provided', () => {
    renderControls({
      confidenceThreshold: 0.5,
      onConfidenceThresholdChange: vi.fn(),
    });
    const slider = screen.getByTestId('correlation-threshold');
    expect(slider).toBeInTheDocument();
    expect(slider).toHaveAttribute('aria-valuenow', '0.5');
    expect(screen.getByTestId('correlation-threshold-value')).toHaveTextContent(
      '50%',
    );
  });

  it('calls onConfidenceThresholdChange with the parsed number on change', () => {
    const onChange = vi.fn();
    renderControls({
      confidenceThreshold: 0.5,
      onConfidenceThresholdChange: onChange,
    });
    const slider = screen.getByTestId('correlation-threshold');
    fireEvent.change(slider, { target: { value: '0.75' } });
    expect(onChange).toHaveBeenCalledWith(0.75);
  });
});
