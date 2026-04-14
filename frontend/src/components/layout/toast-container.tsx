import { useCallback, useEffect, useRef, useState } from 'react';
import { useToastStore } from '@/stores/toast-store';
import type { Toast, ToastType } from '@/stores/toast-store';

const ICON_MAP: Record<ToastType, React.ReactElement> = {
  success: (
    <svg
      className="h-5 w-5 text-green-500"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
    </svg>
  ),
  error: (
    <svg
      className="h-5 w-5 text-red-500"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M6 18L18 6M6 6l12 12"
      />
    </svg>
  ),
  warning: (
    <svg
      className="h-5 w-5 text-amber-500"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    </svg>
  ),
  info: (
    <svg
      className="h-5 w-5 text-blue-500"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      strokeWidth={2}
    >
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
      />
    </svg>
  ),
};

const BG_MAP: Record<ToastType, string> = {
  success:
    'border-green-200 bg-green-50 dark:border-green-800 ' + 'dark:bg-green-950',
  error: 'border-red-200 bg-red-50 dark:border-red-800 ' + 'dark:bg-red-950',
  warning:
    'border-amber-200 bg-amber-50 dark:border-amber-800 ' + 'dark:bg-amber-950',
  info: 'border-blue-200 bg-blue-50 dark:border-blue-800 ' + 'dark:bg-blue-950',
};

function ToastItem(props: {
  toast: Toast;
  onDismiss: (id: string) => void;
}): React.ReactElement {
  const { toast, onDismiss } = props;
  const [visible, setVisible] = useState(false);
  const mountedRef = useRef(true);

  useEffect(() => {
    // trigger enter animation on next frame
    const raf = requestAnimationFrame(() => {
      if (mountedRef.current) {
        setVisible(true);
      }
    });
    return () => {
      mountedRef.current = false;
      cancelAnimationFrame(raf);
    };
  }, []);

  return (
    <div
      role="alert"
      aria-live="polite"
      data-testid={`toast-${toast.id}`}
      className={`flex items-start gap-3 rounded-lg border px-4 py-3 shadow-md transition-all duration-300 ${BG_MAP[toast.type]} ${
        visible ? 'translate-x-0 opacity-100' : 'translate-x-4 opacity-0'
      }`}
    >
      <span className="mt-0.5 shrink-0" aria-hidden="true">
        {ICON_MAP[toast.type]}
      </span>
      <p className="flex-1 text-sm text-foreground">{toast.message}</p>
      <button
        type="button"
        onClick={() => onDismiss(toast.id)}
        aria-label="Dismiss notification"
        className="shrink-0 text-muted-foreground hover:text-foreground"
      >
        <svg
          className="h-4 w-4"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M6 18L18 6M6 6l12 12"
          />
        </svg>
      </button>
    </div>
  );
}

export function ToastContainer(): React.ReactElement | null {
  const toasts = useToastStore((s) => s.toasts);
  const removeToast = useToastStore((s) => s.removeToast);

  // dismiss most recent toast on Escape
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape' && toasts.length > 0) {
        removeToast(toasts[toasts.length - 1].id);
      }
    },
    [toasts, removeToast],
  );

  useEffect(() => {
    if (toasts.length === 0) return;
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [toasts.length, handleKeyDown]);

  if (toasts.length === 0) {
    return null;
  }

  return (
    <div
      data-testid="toast-container"
      aria-label="Notifications"
      className="pointer-events-none fixed bottom-4 right-4 z-50 flex flex-col gap-2"
    >
      {toasts.map((t) => (
        <div key={t.id} className="pointer-events-auto">
          <ToastItem toast={t} onDismiss={removeToast} />
        </div>
      ))}
    </div>
  );
}
