/// <reference types="@testing-library/jest-dom" />
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// captured listener callbacks keyed by event name. the mock below
// pushes into this map so each test can fire a payload synchronously.
type Listener = (event: { payload: unknown }) => void;
const listeners = new Map<string, Set<Listener>>();

vi.mock('@tauri-apps/api/event', () => ({
  listen: vi.fn(async (event: string, cb: Listener) => {
    let set = listeners.get(event);
    if (!set) {
      set = new Set();
      listeners.set(event, set);
    }
    set.add(cb);
    return () => {
      set?.delete(cb);
    };
  }),
}));

vi.mock('@/lib/tauri-bridge', () => ({
  restartBackend: vi.fn(async () => undefined),
  exportDiagnostics: vi.fn(async () => '/tmp/loom-diagnostics.zip'),
  getLogPaths: vi.fn(async () => ({
    shellLogDir: '/home/user/.local/share/io.loom.desktop/logs',
    backendLogDir: '/home/user/.loom/data/logs',
  })),
}));

import { BackendBootGate } from './backend-boot-gate';
import {
  exportDiagnostics,
  getLogPaths,
  restartBackend,
} from '@/lib/tauri-bridge';

function emit(event: string, payload: unknown): void {
  const set = listeners.get(event);
  if (!set) return;
  for (const cb of set) cb({ payload });
}

beforeEach(() => {
  listeners.clear();
  vi.clearAllMocks();
  // force the tauri-detection branch so the hook does not short-
  // circuit to ready in jsdom.
  (window as unknown as { __TAURI_INTERNALS__: unknown }).__TAURI_INTERNALS__ =
    {};
});

afterEach(() => {
  delete (window as unknown as { __TAURI_INTERNALS__?: unknown })
    .__TAURI_INTERNALS__;
});

describe('BackendBootGate', () => {
  it('renders the boot panel while waiting for backend-ready', async () => {
    render(
      <BackendBootGate>
        <div>app contents</div>
      </BackendBootGate>,
    );

    expect(await screen.findByText(/Loom is starting/i)).toBeInTheDocument();
    expect(screen.queryByText('app contents')).not.toBeInTheDocument();
  });

  it('swaps to children when backend-ready fires', async () => {
    render(
      <BackendBootGate>
        <div>app contents</div>
      </BackendBootGate>,
    );

    await screen.findByText(/Loom is starting/i);

    await act(async () => {
      emit('backend-ready', null);
    });

    expect(await screen.findByText('app contents')).toBeInTheDocument();
    expect(screen.queryByText(/Loom is starting/i)).not.toBeInTheDocument();
  });

  it('renders the error block and a retry button on backend-error', async () => {
    const user = userEvent.setup();
    render(
      <BackendBootGate>
        <div>app contents</div>
      </BackendBootGate>,
    );

    await screen.findByText(/Loom is starting/i);

    await act(async () => {
      emit('backend-error', 'sidecar exited: missing module uvicorn');
    });

    expect(
      await screen.findByText(/sidecar exited: missing module uvicorn/),
    ).toBeInTheDocument();

    const retry = screen.getByRole('button', { name: /retry/i });
    await user.click(retry);

    await waitFor(() => {
      expect(restartBackend).toHaveBeenCalledTimes(1);
    });
    expect(screen.getByText(/Loom is starting/i)).toBeInTheDocument();
  });

  it('shows elapsed progress once a slow boot passes the threshold', async () => {
    render(
      <BackendBootGate>
        <div>app contents</div>
      </BackendBootGate>,
    );

    await screen.findByText(/Loom is starting/i);
    // early progress stays quiet: a normal boot never shows a timer
    await act(async () => {
      emit('backend-boot-progress', { elapsedSecs: 3, timeoutSecs: 180 });
    });
    expect(screen.queryByText(/elapsed/i)).not.toBeInTheDocument();

    await act(async () => {
      emit('backend-boot-progress', { elapsedSecs: 42, timeoutSecs: 180 });
    });
    expect(await screen.findByText(/42s elapsed/i)).toBeInTheDocument();
    expect(
      screen.getByText(/first launch on this machine can take/i),
    ).toBeInTheDocument();
  });

  it('shows log locations and exports diagnostics from the error panel', async () => {
    const user = userEvent.setup();
    render(
      <BackendBootGate>
        <div>app contents</div>
      </BackendBootGate>,
    );

    await screen.findByText(/Loom is starting/i);
    await act(async () => {
      emit('backend-error', 'loom-boot-error: port 127.0.0.1:8000 in use');
    });

    expect(
      await screen.findByText(/io\.loom\.desktop\/logs/),
    ).toBeInTheDocument();
    expect(screen.getByText(/\.loom\/data\/logs/)).toBeInTheDocument();
    expect(getLogPaths).toHaveBeenCalled();

    const exportButton = screen.getByRole('button', {
      name: /export diagnostics/i,
    });
    await user.click(exportButton);

    await waitFor(() => {
      expect(exportDiagnostics).toHaveBeenCalledTimes(1);
    });
    expect(
      await screen.findByText(/loom-diagnostics\.zip/),
    ).toBeInTheDocument();
  });

  it('still renders the error panel when log paths are unavailable', async () => {
    vi.mocked(getLogPaths).mockRejectedValueOnce(new Error('no shell'));
    render(
      <BackendBootGate>
        <div>app contents</div>
      </BackendBootGate>,
    );

    await screen.findByText(/Loom is starting/i);
    await act(async () => {
      emit('backend-error', 'backend exited unexpectedly');
    });

    expect(
      await screen.findByText(/backend exited unexpectedly/),
    ).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /retry/i })).toBeInTheDocument();
  });
});
