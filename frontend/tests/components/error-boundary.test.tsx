import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import {
  ErrorBoundary,
  ErrorFallback,
} from '@/components/layout/error-boundary';

// component that throws on render
function ThrowingChild(props: {
  shouldThrow: boolean;
}): React.ReactElement {
  if (props.shouldThrow) {
    throw new Error('test explosion');
  }
  return <p>Child rendered</p>;
}

// suppress console.error noise from error boundary
const originalError = console.error;
beforeEach(() => {
  console.error = vi.fn();
});
afterEach(() => {
  console.error = originalError;
});

describe('ErrorBoundary', () => {
  it('renders children when there is no error', () => {
    render(
      <ErrorBoundary>
        <ThrowingChild shouldThrow={false} />
      </ErrorBoundary>,
    );
    expect(
      screen.getByText('Child rendered'),
    ).toBeInTheDocument();
  });

  it('renders fallback ui when child throws', () => {
    render(
      <ErrorBoundary>
        <ThrowingChild shouldThrow={true} />
      </ErrorBoundary>,
    );
    expect(
      screen.getByText('Something went wrong'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('test explosion'),
    ).toBeInTheDocument();
  });

  it('renders custom fallback when provided', () => {
    render(
      <ErrorBoundary fallback={<p>Custom fallback</p>}>
        <ThrowingChild shouldThrow={true} />
      </ErrorBoundary>,
    );
    expect(
      screen.getByText('Custom fallback'),
    ).toBeInTheDocument();
  });

  it('resets error state on try again click', async () => {
    const user = userEvent.setup();

    // we need a stateful wrapper so we can stop throwing
    let shouldThrow = true;

    function ConditionalThrower(): React.ReactElement {
      if (shouldThrow) {
        throw new Error('boom');
      }
      return <p>Recovered</p>;
    }

    render(
      <ErrorBoundary>
        <ConditionalThrower />
      </ErrorBoundary>,
    );

    expect(
      screen.getByText('Something went wrong'),
    ).toBeInTheDocument();

    // stop throwing, then click try again
    shouldThrow = false;
    await user.click(screen.getByText('Try Again'));

    expect(screen.getByText('Recovered')).toBeInTheDocument();
  });

  it('has accessible role="alert" on fallback', () => {
    render(
      <ErrorBoundary>
        <ThrowingChild shouldThrow={true} />
      </ErrorBoundary>,
    );
    expect(screen.getByRole('alert')).toBeInTheDocument();
  });
});

describe('ErrorFallback', () => {
  it('renders error message', () => {
    const onReset = vi.fn();
    render(
      <ErrorFallback
        error={new Error('details here')}
        onReset={onReset}
      />,
    );
    expect(
      screen.getByText('details here'),
    ).toBeInTheDocument();
  });

  it('calls onReset when try again is clicked', async () => {
    const user = userEvent.setup();
    const onReset = vi.fn();
    render(
      <ErrorFallback error={null} onReset={onReset} />,
    );
    await user.click(screen.getByText('Try Again'));
    expect(onReset).toHaveBeenCalledOnce();
  });
});
