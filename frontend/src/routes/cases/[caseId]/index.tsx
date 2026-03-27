import * as Tabs from '@radix-ui/react-tabs';
import { useParams } from 'react-router-dom';
import { QueryError } from '@/components/layout/query-error';
import { useCase, useCaseMembers } from '@/hooks/use-case';

const statusColors: Record<string, string> = {
  active:
    'bg-green-100 text-green-800 dark:bg-green-900 ' + 'dark:text-green-200',
  archived:
    'bg-gray-100 text-gray-800 dark:bg-gray-900 ' + 'dark:text-gray-200',
  exported:
    'bg-blue-100 text-blue-800 dark:bg-blue-900 ' + 'dark:text-blue-200',
};

export function CaseDetailPage(): React.ReactElement {
  const { caseId } = useParams<{ caseId: string }>();
  const {
    data: caseData,
    isLoading,
    isError,
    refetch,
  } = useCase(caseId ?? '');
  const { data: members } = useCaseMembers(caseId ?? '');

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
      <div className="animate-pulse space-y-4">
        <div className="h-8 w-1/3 rounded bg-muted" />
        <div className="h-4 w-2/3 rounded bg-muted" />
        <div className="h-64 rounded bg-muted" />
      </div>
    );
  }

  const colorClass = statusColors[caseData.status] ?? statusColors['archived'];

  return (
    <div className="space-y-6">
      {/* case header */}
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold text-foreground">
            {caseData.name}
          </h1>
          <span
            data-testid="status-badge"
            className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${colorClass}`}
          >
            {caseData.status}
          </span>
        </div>
        {caseData.description && (
          <p className="mt-1 text-sm text-muted-foreground">
            {caseData.description}
          </p>
        )}
      </div>

      {/* tabs */}
      <Tabs.Root defaultValue="overview">
        <Tabs.List className="flex gap-1 border-b border-border">
          <Tabs.Trigger
            value="overview"
            className="px-3 py-2 text-sm text-muted-foreground data-[state=active]:border-b-2 data-[state=active]:border-primary data-[state=active]:text-foreground"
          >
            Overview
          </Tabs.Trigger>
          <Tabs.Trigger
            value="members"
            className="px-3 py-2 text-sm text-muted-foreground data-[state=active]:border-b-2 data-[state=active]:border-primary data-[state=active]:text-foreground"
          >
            Members
          </Tabs.Trigger>
        </Tabs.List>

        {/* overview tab */}
        <Tabs.Content value="overview" className="pt-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="bg-card rounded-lg border border-border p-4">
              <p className="text-xs text-muted-foreground">Assets</p>
              <p className="text-2xl font-semibold text-foreground">
                {caseData.assetCount}
              </p>
            </div>
            <div className="bg-card rounded-lg border border-border p-4">
              <p className="text-xs text-muted-foreground">Events</p>
              <p className="text-2xl font-semibold text-foreground">
                {caseData.eventCount}
              </p>
            </div>
            <div className="bg-card rounded-lg border border-border p-4">
              <p className="text-xs text-muted-foreground">Members</p>
              <p className="text-2xl font-semibold text-foreground">
                {members?.length ?? 0}
              </p>
            </div>
          </div>

          {/* recent activity placeholder */}
          <div className="mt-6">
            <h2 className="text-sm font-medium text-foreground">
              Recent Activity
            </h2>
            <p className="mt-2 text-sm text-muted-foreground">
              No recent activity to display.
            </p>
          </div>
        </Tabs.Content>

        {/* members tab */}
        <Tabs.Content value="members" className="pt-4">
          {!members || members.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No members assigned to this case.
            </p>
          ) : (
            <ul className="divide-y divide-border">
              {members.map((m) => (
                <li
                  key={m.id}
                  className="flex items-center justify-between py-3"
                >
                  <div>
                    <p className="text-sm font-medium text-foreground">
                      {m.displayName}
                    </p>
                    <p className="text-xs text-muted-foreground">{m.email}</p>
                  </div>
                  <span className="text-xs font-medium text-muted-foreground">
                    {m.role}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Tabs.Content>
      </Tabs.Root>
    </div>
  );
}
