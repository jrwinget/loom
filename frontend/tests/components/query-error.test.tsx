/// <reference types="@testing-library/jest-dom" />
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe } from 'jest-axe';
import { describe, expect, it, vi } from 'vitest';
import { QueryError } from '@/components/layout/query-error';

describe('QueryError', () => {
  it('renders the failure message', () => {
    render(<QueryError message="Failed to load cases" />);

    expect(screen.getByRole('alert')).toHaveTextContent('Failed to load cases');
  });

  it('omits the retry control when no handler is provided', () => {
    render(<QueryError message="Failed to load" />);

    expect(screen.queryByTestId('query-error-retry')).not.toBeInTheDocument();
  });

  it('invokes the retry handler when the retry button is clicked', async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<QueryError message="Failed to load" onRetry={onRetry} />);

    await user.click(screen.getByRole('button', { name: 'Try again' }));

    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('has no accessibility violations', async () => {
    const { container } = render(
      <QueryError message="Failed to load" onRetry={vi.fn()} />,
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});
