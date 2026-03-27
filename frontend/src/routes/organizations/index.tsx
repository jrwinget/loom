import { QueryError } from '@/components/layout/query-error';
import { OrgList } from '@/components/organization/org-list';
import { useOrganizations, useCreateOrg } from '@/hooks/use-organizations';

export function OrganizationsPage(): React.ReactElement {
  const {
    data: organizations,
    isLoading,
    isError,
    refetch,
  } = useOrganizations();
  const createOrg = useCreateOrg();

  const handleCreateOrg = (name: string, description: string): void => {
    createOrg.mutate({ name, description });
  };

  return (
    <div className="mx-auto max-w-5xl p-6">
      {isError && (
        <QueryError
          message="Failed to load organizations."
          onRetry={() => void refetch()}
        />
      )}

      {!isError && (
        <OrgList
          organizations={organizations ?? []}
          isLoading={isLoading}
          onCreateOrg={handleCreateOrg}
        />
      )}
    </div>
  );
}
