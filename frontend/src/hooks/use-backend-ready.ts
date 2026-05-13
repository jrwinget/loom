import { useCallback, useEffect, useState } from 'react';

export interface BackendReadyState {
  status: 'booting' | 'ready' | 'error';
  error?: string;
}

export interface UseBackendReadyResult extends BackendReadyState {
  // forces the gate back to ``booting`` while a retry is in flight.
  // the next backend-ready / backend-error event drives the
  // subsequent state transition.
  reset: () => void;
}

// outside tauri (vite dev against a live backend) there is no shell
// to emit ready/error, so callers see ready immediately and the rest
// of the app renders unchanged.
function isTauriRuntime(): boolean {
  return (
    typeof window !== 'undefined' &&
    typeof (window as unknown as { __TAURI_INTERNALS__?: unknown })
      .__TAURI_INTERNALS__ !== 'undefined'
  );
}

export function useBackendReady(): UseBackendReadyResult {
  const [state, setState] = useState<BackendReadyState>(() =>
    isTauriRuntime() ? { status: 'booting' } : { status: 'ready' },
  );

  useEffect(() => {
    if (!isTauriRuntime()) return;

    let cancelled = false;
    const unlisteners: Array<() => void> = [];

    (async () => {
      const mod = (await import('@tauri-apps/api/event')) as {
        listen: <T>(
          event: string,
          cb: (e: { payload: T }) => void,
        ) => Promise<() => void>;
      };

      const offReady = await mod.listen<null>('backend-ready', () => {
        if (cancelled) return;
        setState({ status: 'ready' });
      });
      unlisteners.push(offReady);

      const offError = await mod.listen<string>('backend-error', (event) => {
        if (cancelled) return;
        const message =
          typeof event.payload === 'string' && event.payload.length > 0
            ? event.payload
            : 'backend failed to start';
        setState({ status: 'error', error: message });
      });
      unlisteners.push(offError);
    })().catch(() => {
      // if the event module fails to load we surface an error rather
      // than leaving the user stuck on the boot panel.
      if (!cancelled) {
        setState({
          status: 'error',
          error: 'failed to subscribe to backend boot events',
        });
      }
    });

    return () => {
      cancelled = true;
      for (const off of unlisteners) off();
    };
  }, []);

  const reset = useCallback(() => {
    if (isTauriRuntime()) setState({ status: 'booting' });
  }, []);

  return { ...state, reset };
}
