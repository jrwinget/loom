import * as Tabs from '@radix-ui/react-tabs';
import { useNavigate, useParams } from 'react-router-dom';
import { CaseDangerZone } from '@/components/case/case-danger-zone';
import { QueryError } from '@/components/layout/query-error';
import { useCase, useCaseMembers } from '@/hooks/use-case';
import { useCaseAudit } from '@/hooks/use-audit';
import type { AuditEntry } from '@/hooks/use-audit';
import { useFirstRunStatus } from '@/hooks/use-first-run';

function formatAuditTimestamp(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function describeAuditEntry(entry: AuditEntry): string {
  const action = entry.action.replace(/_/g, ' ');
  const resource = entry.resourceType.replace(/_/g, ' ');
  return `${action} on ${resource}`;
}

export function CaseDetailPage(): React.ReactElement {
  const { caseId } = useParams<{ caseId: string }>();
  const navigate = useNavigate();
  const safeId = caseId ?? '';
  const { data: caseData, isLoading, isError, refetch } = useCase(safeId);
  const { data: members } = useCaseMembers(safeId);
  const { data: auditData } = useCaseAudit(safeId);
  const isLite = useFirstRunStatus().data?.deploymentProfile === 'lite';

  if (isError) {
    return (
      <div className="p-6">
        <QueryError
          message="Failed to load case details."
          onRetry={() => void refetch()}
        />
      </div>
    );
  }

  if (isLoading || !caseData) {
    return (
      <div
        aria-busy="true"
        aria-label="Loading case details"
        className="animate-pulse space-y-4"
      >
        <div className="bg-muted h-8 w-1/3 rounded" />
        <div className="bg-muted h-4 w-2/3 rounded" />
        <div className="bg-muted h-64 rounded" />
      </div>
    );
  }

  const recentActivity = auditData?.items ?? [];

  return (
    <div className="space-y-6">
      {caseData.description && (
        <p className="text-muted-foreground text-sm">{caseData.description}</p>
      )}

      <Tabs.Root defaultValue="overview">
        <Tabs.List className="border-border flex gap-1 border-b">
          <Tabs.Trigger
            value="overview"
            className={
              'text-muted-foreground px-3 py-2 text-sm ' +
              'data-[state=active]:border-b-2 ' +
              'data-[state=active]:border-primary ' +
              'data-[state=active]:text-foreground'
            }
          >
            Overview
          </Tabs.Trigger>
          {!isLite && (
            <Tabs.Trigger
              value="members"
              className={
                'text-muted-foreground px-3 py-2 text-sm ' +
                'data-[state=active]:border-b-2 ' +
                'data-[state=active]:border-primary ' +
                'data-[state=active]:text-foreground'
              }
            >
              Members
            </Tabs.Trigger>
          )}
        </Tabs.List>

        <Tabs.Content value="overview" className="pt-4">
          <div className={'grid grid-cols-1 gap-4 sm:grid-cols-3'}>
            <div className={'border-border bg-card rounded-lg border p-4'}>
              <p className="text-muted-foreground text-xs">Assets</p>
              <p className="text-foreground text-2xl font-semibold">
                {caseData.assetCount}
              </p>
            </div>
            <div className={'border-border bg-card rounded-lg border p-4'}>
              <p className="text-muted-foreground text-xs">Events</p>
              <p className="text-foreground text-2xl font-semibold">
                {caseData.eventCount}
              </p>
            </div>
            <div className={'border-border bg-card rounded-lg border p-4'}>
              <p className="text-muted-foreground text-xs">Members</p>
              <p className="text-foreground text-2xl font-semibold">
                {members?.length ?? 0}
              </p>
            </div>
          </div>

          <div className="mt-6">
            <h2 className="text-foreground text-sm font-medium">
              Recent Activity
            </h2>
            {recentActivity.length === 0 ? (
              <p className="text-muted-foreground mt-2 text-sm">
                No recent activity to display.
              </p>
            ) : (
              <ul data-testid="activity-feed" className="mt-2 space-y-3">
                {recentActivity.map((entry) => (
                  <li key={entry.id} className="flex items-start gap-3">
                    <div
                      className={
                        'mt-1.5 h-2 w-2 shrink-0 ' + 'bg-primary rounded-full'
                      }
                    />
                    <div>
                      <p className="text-foreground text-sm">
                        {describeAuditEntry(entry)}
                      </p>
                      <p className="text-muted-foreground text-xs">
                        {formatAuditTimestamp(entry.timestamp)}
                      </p>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <CaseDangerZone
            caseData={caseData}
            onPurged={() => void navigate('/cases')}
          />
        </Tabs.Content>

        {!isLite && (
          <Tabs.Content value="members" className="pt-4">
            {!members || members.length === 0 ? (
              <p className="text-muted-foreground text-sm">
                No members assigned to this case.
              </p>
            ) : (
              <ul className="divide-border divide-y">
                {members.map((m) => (
                  <li
                    key={m.id}
                    className={'flex items-center justify-between py-3'}
                  >
                    <div>
                      <p className="text-foreground text-sm font-medium">
                        {m.displayName}
                      </p>
                      <p className="text-muted-foreground text-xs">{m.email}</p>
                    </div>
                    <span
                      className={'text-muted-foreground text-xs font-medium'}
                    >
                      {m.role}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Tabs.Content>
        )}
      </Tabs.Root>
    </div>
  );
}
