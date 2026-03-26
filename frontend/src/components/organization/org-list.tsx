import { useState } from 'react';
import type { Organization } from '@/types/organization';

interface OrgListProps {
  organizations: Organization[];
  isLoading: boolean;
  onCreateOrg: (name: string, description: string) => void;
}

export function OrgList({
  organizations,
  isLoading,
  onCreateOrg,
}: OrgListProps): React.ReactElement {
  const [showDialog, setShowDialog] = useState(false);
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');

  const handleSubmit = (e: React.FormEvent): void => {
    e.preventDefault();
    onCreateOrg(name, description);
    setName('');
    setDescription('');
    setShowDialog(false);
  };

  if (isLoading) {
    return (
      <div data-testid="org-loading" className="space-y-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            data-testid="org-skeleton"
            className="h-20 animate-pulse rounded-lg bg-muted"
          />
        ))}
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-xl font-semibold text-foreground">Organizations</h2>
        <button
          data-testid="create-org-btn"
          onClick={() => setShowDialog(true)}
          className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90"
        >
          Create Organization
        </button>
      </div>

      {organizations.length === 0 ? (
        <div
          data-testid="org-empty-state"
          className="flex flex-col items-center justify-center py-12"
        >
          <p className="text-muted-foreground">No organizations yet</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {organizations.map((org) => (
            <div
              key={org.id}
              data-testid="org-card"
              className="bg-card rounded-lg border border-border p-4"
            >
              <div className="flex items-center justify-between">
                <h3 className="font-medium text-foreground">{org.name}</h3>
                <span
                  data-testid="member-count-badge"
                  className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
                >
                  {org.memberCount} members
                </span>
              </div>
              {org.description && (
                <p className="mt-1 text-sm text-muted-foreground">
                  {org.description}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      {showDialog && (
        <div
          data-testid="create-org-dialog"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50"
        >
          <form
            onSubmit={handleSubmit}
            className="bg-card w-full max-w-md rounded-lg p-6"
          >
            <h3 className="mb-4 text-lg font-semibold">Create Organization</h3>
            <div className="mb-4">
              <label
                htmlFor="org-name"
                className="mb-1 block text-sm text-muted-foreground"
              >
                Name
              </label>
              <input
                id="org-name"
                data-testid="org-name-input"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                required
              />
            </div>
            <div className="mb-4">
              <label
                htmlFor="org-description"
                className="mb-1 block text-sm text-muted-foreground"
              >
                Description
              </label>
              <textarea
                id="org-description"
                data-testid="org-description-input"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                rows={3}
              />
            </div>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowDialog(false)}
                className="rounded-md px-4 py-2 text-sm text-muted-foreground hover:bg-muted"
              >
                Cancel
              </button>
              <button
                type="submit"
                data-testid="org-submit-btn"
                className="rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground hover:bg-primary/90"
              >
                Create
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  );
}
