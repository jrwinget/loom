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
            className="bg-muted h-20 animate-pulse rounded-lg"
          />
        ))}
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6 flex items-center justify-between">
        <h2 className="text-foreground text-xl font-semibold">Organizations</h2>
        <button
          data-testid="create-org-btn"
          onClick={() => setShowDialog(true)}
          className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-md px-4 py-2 text-sm"
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
              className="border-border bg-card rounded-lg border p-4"
            >
              <div className="flex items-center justify-between">
                <h3 className="text-foreground font-medium">{org.name}</h3>
                <span
                  data-testid="member-count-badge"
                  className="bg-muted text-muted-foreground rounded-full px-2 py-0.5 text-xs"
                >
                  {org.memberCount} members
                </span>
              </div>
              {org.description && (
                <p className="text-muted-foreground mt-1 text-sm">
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
                className="text-muted-foreground mb-1 block text-sm"
              >
                Name
              </label>
              <input
                id="org-name"
                data-testid="org-name-input"
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="border-border bg-background w-full rounded-md border px-3 py-2 text-sm"
                required
              />
            </div>
            <div className="mb-4">
              <label
                htmlFor="org-description"
                className="text-muted-foreground mb-1 block text-sm"
              >
                Description
              </label>
              <textarea
                id="org-description"
                data-testid="org-description-input"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="border-border bg-background w-full rounded-md border px-3 py-2 text-sm"
                rows={3}
              />
            </div>
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowDialog(false)}
                className="text-muted-foreground hover:bg-muted rounded-md px-4 py-2 text-sm"
              >
                Cancel
              </button>
              <button
                type="submit"
                data-testid="org-submit-btn"
                className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-md px-4 py-2 text-sm"
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
