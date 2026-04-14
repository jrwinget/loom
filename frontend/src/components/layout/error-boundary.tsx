import { Component, createRef, useEffect, useRef } from 'react';
import type { ErrorInfo, ReactNode } from 'react';

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<
  ErrorBoundaryProps,
  ErrorBoundaryState
> {
  private headingRef = createRef<HTMLHeadingElement>();

  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('ErrorBoundary caught:', error, info);
  }

  componentDidUpdate(
    _prevProps: ErrorBoundaryProps,
    prevState: ErrorBoundaryState,
  ): void {
    if (this.state.hasError && !prevState.hasError) {
      this.headingRef.current?.focus();
    }
  }

  handleReset = (): void => {
    this.setState({ hasError: false, error: null });
  };

  render(): ReactNode {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <ErrorFallback
          error={this.state.error}
          onReset={this.handleReset}
          headingRef={this.headingRef}
        />
      );
    }

    return this.props.children;
  }
}

interface ErrorFallbackProps {
  error: Error | null;
  onReset: () => void;
  headingRef?: React.RefObject<HTMLHeadingElement>;
}

export function ErrorFallback(props: ErrorFallbackProps): React.ReactElement {
  const { error, onReset, headingRef } = props;
  const localRef = useRef<HTMLHeadingElement>(null);
  const ref = headingRef ?? localRef;

  // focus heading on mount when used standalone
  useEffect(() => {
    if (!headingRef) {
      localRef.current?.focus();
    }
  }, [headingRef]);

  return (
    <div
      role="alert"
      aria-live="assertive"
      className="flex min-h-[400px] items-center justify-center p-6"
    >
      <div className="max-w-md text-center">
        <div
          className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-red-100 dark:bg-red-900"
          aria-hidden="true"
        >
          <svg
            className="h-6 w-6 text-red-600 dark:text-red-300"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        </div>
        <h2
          ref={ref}
          tabIndex={-1}
          className="text-lg font-semibold text-foreground focus:outline-none"
        >
          Something went wrong
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          An unexpected error occurred. You can try again or reload the page.
        </p>
        {error?.message && import.meta.env.DEV && (
          <p className="mt-3 rounded bg-muted px-3 py-2 text-xs text-muted-foreground">
            {error.message}
          </p>
        )}
        <div className="mt-6 flex items-center justify-center gap-3">
          <button
            type="button"
            onClick={onReset}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            Try Again
          </button>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded-md border border-border px-4 py-2 text-sm font-medium text-foreground hover:bg-accent"
          >
            Reload Page
          </button>
        </div>
      </div>
    </div>
  );
}
