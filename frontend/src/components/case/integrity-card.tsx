import { useVerifyCase } from '@/hooks/use-integrity';

interface IntegrityCardProps {
  caseId: string;
}

/**
 * case-wide integrity verification. an attorney signing a
 * declaration needs to actually run the check the declaration
 * describes, and see which assets failed.
 */
export function IntegrityCard(props: IntegrityCardProps): React.ReactElement {
  const { caseId } = props;
  const verifyCase = useVerifyCase(caseId);
  const result = verifyCase.data;

  return (
    <div
      className="border-border rounded-lg border p-4"
      data-testid="integrity-card"
    >
      <h3 className="text-foreground text-sm font-semibold">
        Evidence integrity
      </h3>
      <p className="text-muted-foreground mt-1 text-xs">
        Re-hashes every stored original and compares it against the digest
        recorded at intake.
      </p>

      <button
        type="button"
        onClick={() => verifyCase.mutate()}
        disabled={verifyCase.isPending}
        data-testid="verify-case-btn"
        className="bg-primary text-primary-foreground hover:bg-primary/90 mt-3 rounded-md px-3 py-2 text-sm disabled:opacity-50"
      >
        {verifyCase.isPending ? 'Verifying…' : 'Verify all evidence'}
      </button>

      {result && (
        <div className="mt-3 text-xs" data-testid="verify-case-summary">
          <p className="text-foreground">
            {result.passedCount} of {result.totalAssets} verified
            {result.failedCount > 0 ? `, ${result.failedCount} failed` : ''}
          </p>
          {result.failedCount > 0 && (
            <ul
              className="text-destructive mt-1 space-y-0.5"
              data-testid="verify-case-failures"
            >
              {result.results
                .filter((r) => !r.passed)
                .map((r) => (
                  <li key={r.assetId}>FAILED: {r.storageKey}</li>
                ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
