// persistent notice shown on every case page while a litigation hold
// is active. the hold is a preservation lock (destructive actions are
// refused server-side); this banner keeps that state visible so no
// one is surprised by a disabled destroy button.

import type { Case } from '@/types';

export function formatHoldDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

interface CaseHoldBannerProps {
  caseData: Case;
}

export function CaseHoldBanner({
  caseData,
}: CaseHoldBannerProps): React.ReactElement | null {
  if (!caseData.holdActive) return null;

  return (
    <div
      role="status"
      data-testid="case-hold-banner"
      className={
        'rounded-md border border-amber-400 bg-amber-50 px-4 py-3 ' +
        'text-sm text-amber-900 dark:border-amber-700 ' +
        'dark:bg-amber-950 dark:text-amber-200'
      }
    >
      <p className="font-medium">
        This case is under litigation hold — destructive actions are disabled.
      </p>
      {caseData.holdReason && (
        <p className="mt-1">Reason: {caseData.holdReason}</p>
      )}
      {caseData.holdSetAt && (
        <p className="mt-1 text-xs opacity-80">
          Hold set {formatHoldDate(caseData.holdSetAt)}
        </p>
      )}
    </div>
  );
}
