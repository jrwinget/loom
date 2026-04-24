import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// each test must re-import the module after mutating the global so
// the module-level ``isTauri`` constant is re-evaluated.
async function freshImport(): Promise<
  typeof import('@/lib/tauri-bridge')
> {
  vi.resetModules();
  return import('@/lib/tauri-bridge');
}

describe('tauri-bridge', () => {
  beforeEach(() => {
    delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
  });

  afterEach(() => {
    delete (window as unknown as Record<string, unknown>).__TAURI_INTERNALS__;
  });

  describe('isTauri', () => {
    it('is false when __TAURI_INTERNALS__ is missing', async () => {
      const mod = await freshImport();
      expect(mod.isTauri).toBe(false);
    });

    it('is true when __TAURI_INTERNALS__ is present', async () => {
      (window as unknown as { __TAURI_INTERNALS__: unknown }).__TAURI_INTERNALS__ =
        { invoke: vi.fn() };
      const mod = await freshImport();
      expect(mod.isTauri).toBe(true);
    });
  });

  describe('pickDirectory (non-tauri)', () => {
    it('falls back to window.prompt when not in tauri', async () => {
      const promptSpy = vi
        .spyOn(window, 'prompt')
        .mockReturnValue('/mnt/evidence');
      const mod = await freshImport();
      const result = await mod.pickDirectory();
      expect(promptSpy).toHaveBeenCalled();
      expect(result).toBe('/mnt/evidence');
      promptSpy.mockRestore();
    });

    it('returns null when the user cancels the prompt', async () => {
      const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue(null);
      const mod = await freshImport();
      const result = await mod.pickDirectory();
      expect(result).toBeNull();
      promptSpy.mockRestore();
    });

    it('returns null on empty / whitespace input', async () => {
      const promptSpy = vi.spyOn(window, 'prompt').mockReturnValue('   ');
      const mod = await freshImport();
      expect(await mod.pickDirectory()).toBeNull();
      promptSpy.mockRestore();
    });
  });

  describe('tauriDiskUsage (non-tauri)', () => {
    it('returns null when not running under tauri', async () => {
      const mod = await freshImport();
      expect(await mod.tauriDiskUsage('/any/path')).toBeNull();
    });
  });

  describe('persistDataDirectory (non-tauri)', () => {
    it('is a no-op when not running under tauri', async () => {
      const mod = await freshImport();
      await expect(mod.persistDataDirectory('/tmp/x')).resolves.toBeUndefined();
    });
  });

  describe('restartBackend (non-tauri)', () => {
    it('is a no-op when not running under tauri', async () => {
      const mod = await freshImport();
      await expect(mod.restartBackend()).resolves.toBeUndefined();
    });
  });
});
