/// <reference types="@testing-library/jest-dom" />
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { axe } from 'jest-axe';
import { beforeEach, describe, expect, it } from 'vitest';
import { ToastContainer } from '@/components/layout/toast-container';
import { useToastStore } from '@/stores/toast-store';
import type { Toast } from '@/stores/toast-store';

function seed(toasts: Toast[]): void {
  useToastStore.setState({ toasts });
}

beforeEach(() => {
  seed([]);
});

describe('ToastContainer', () => {
  it('renders nothing when there are no toasts', () => {
    const { container } = render(<ToastContainer />);

    expect(container).toBeEmptyDOMElement();
  });

  it('renders a toast message from the store', () => {
    seed([{ id: 't1', type: 'success', message: 'Saved', duration: 0 }]);
    render(<ToastContainer />);

    expect(screen.getByText('Saved')).toBeInTheDocument();
  });

  it('removes a toast when its dismiss button is clicked', async () => {
    seed([{ id: 't1', type: 'info', message: 'Heads up', duration: 0 }]);
    const user = userEvent.setup();
    render(<ToastContainer />);

    await user.click(
      screen.getByRole('button', { name: 'Dismiss notification' }),
    );

    expect(useToastStore.getState().toasts).toHaveLength(0);
  });

  it('dismisses the most recent toast on Escape', async () => {
    seed([
      { id: 't1', type: 'info', message: 'First', duration: 0 },
      { id: 't2', type: 'info', message: 'Second', duration: 0 },
    ]);
    const user = userEvent.setup();
    render(<ToastContainer />);

    await user.keyboard('{Escape}');

    expect(useToastStore.getState().toasts.map((t) => t.id)).toEqual(['t1']);
  });

  it('has no accessibility violations', async () => {
    seed([{ id: 't1', type: 'error', message: 'Boom', duration: 0 }]);
    const { container } = render(<ToastContainer />);

    expect(await axe(container)).toHaveNoViolations();
  });
});
