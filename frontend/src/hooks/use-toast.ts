import { useCallback, useMemo } from 'react';
import { useToastStore } from '@/stores/toast-store';

interface ToastActions {
  success: (message: string) => string;
  error: (message: string) => string;
  info: (message: string) => string;
  warning: (message: string) => string;
  dismiss: (id: string) => void;
}

interface UseToastReturn {
  toast: ToastActions;
}

export function useToast(): UseToastReturn {
  const addToast = useToastStore((s) => s.addToast);
  const removeToast = useToastStore((s) => s.removeToast);

  const success = useCallback(
    (message: string) => addToast({ type: 'success', message }),
    [addToast],
  );
  const error = useCallback(
    (message: string) => addToast({ type: 'error', message }),
    [addToast],
  );
  const info = useCallback(
    (message: string) => addToast({ type: 'info', message }),
    [addToast],
  );
  const warning = useCallback(
    (message: string) => addToast({ type: 'warning', message }),
    [addToast],
  );
  const dismiss = useCallback(
    (id: string) => removeToast(id),
    [removeToast],
  );

  const toast = useMemo(
    () => ({ success, error, info, warning, dismiss }),
    [success, error, info, warning, dismiss],
  );

  return { toast };
}
