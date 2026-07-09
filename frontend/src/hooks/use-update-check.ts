import { useEffect, useState } from 'react';
import { checkForUpdate, type UpdateInfo } from '@/lib/tauri-bridge';

// one passive check shortly after launch, then daily for sessions
// that stay open. the delay keeps the check off the boot-gate path.
const INITIAL_DELAY_MS = 15_000;
const RECHECK_INTERVAL_MS = 24 * 60 * 60 * 1000;

export function useUpdateCheck(): {
  update: UpdateInfo | null;
  dismiss: () => void;
} {
  const [update, setUpdate] = useState<UpdateInfo | null>(null);
  const [dismissedVersion, setDismissedVersion] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const run = async () => {
      const found = await checkForUpdate().catch(() => null);
      if (!cancelled && found) setUpdate(found);
    };

    const initial = setTimeout(run, INITIAL_DELAY_MS);
    const recheck = setInterval(run, RECHECK_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearTimeout(initial);
      clearInterval(recheck);
    };
  }, []);

  return {
    update: update && update.version !== dismissedVersion ? update : null,
    dismiss: () => setDismissedVersion(update?.version ?? null),
  };
}
