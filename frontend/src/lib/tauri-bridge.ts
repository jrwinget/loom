// thin bridge to tauri v2 ipc. everything here degrades gracefully
// in a plain web context so the rest of the app does not have to
// branch on runtime.

interface TauriInternals {
  invoke: <T>(cmd: string, args?: Record<string, unknown>) => Promise<T>;
}

declare global {
  interface Window {
    __TAURI_INTERNALS__?: TauriInternals;
  }
}

export const isTauri: boolean =
  typeof window !== 'undefined' &&
  typeof window.__TAURI_INTERNALS__ !== 'undefined';

async function invokeCommand<T>(
  cmd: string,
  args?: Record<string, unknown>,
): Promise<T> {
  if (!isTauri) {
    throw new Error(`tauri not available: cannot invoke "${cmd}"`);
  }
  // prefer the official api when installed; fall back to the raw
  // __TAURI_INTERNALS__ shim otherwise so we don't need a hard dep
  // in the web build.
  try {
    const mod = (await import('@tauri-apps/api/core')) as unknown as {
      invoke: <R>(cmd: string, args?: Record<string, unknown>) => Promise<R>;
    };
    return mod.invoke<T>(cmd, args);
  } catch {
    const internals = window.__TAURI_INTERNALS__;
    if (!internals) {
      throw new Error(`tauri internals missing for "${cmd}"`);
    }
    return internals.invoke<T>(cmd, args);
  }
}

export async function pickDirectory(): Promise<string | null> {
  if (isTauri) {
    const result = await invokeCommand<string | null>('pick_directory');
    return result ?? null;
  }
  // non-tauri dev fallback: prompt for a pasted path so the ui is
  // still exercisable in the vite dev server.
  if (typeof window === 'undefined' || typeof window.prompt !== 'function') {
    return null;
  }
  const entered = window.prompt(
    'Paste an absolute path for the Loom data directory:',
  );
  if (!entered) return null;
  return entered.trim() || null;
}

export interface DiskUsage {
  free: number;
  total: number;
}

export async function tauriDiskUsage(path: string): Promise<DiskUsage | null> {
  if (!isTauri) return null;
  return invokeCommand<DiskUsage>('disk_usage', { path });
}

export async function persistDataDirectory(path: string): Promise<void> {
  if (!isTauri) return;
  await invokeCommand<void>('persist_data_directory', { path });
}

export async function restartBackend(): Promise<void> {
  if (!isTauri) return;
  await invokeCommand<void>('restart_backend');
}
