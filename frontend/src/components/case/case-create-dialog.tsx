import * as Dialog from '@radix-ui/react-dialog';
import { useState } from 'react';
import { useCreateCase } from '@/hooks/use-case';

interface CaseCreateDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CaseCreateDialog(
  props: CaseCreateDialogProps,
): React.ReactElement {
  const { open, onOpenChange } = props;
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const createCase = useCreateCase();

  function handleSubmit(e: React.FormEvent<HTMLFormElement>): void {
    e.preventDefault();
    if (!name.trim()) return;

    createCase.mutate(
      {
        name: name.trim(),
        description: description.trim() || undefined,
      },
      {
        onSuccess: () => {
          setName('');
          setDescription('');
          onOpenChange(false);
        },
      },
    );
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border border-border bg-card p-6 shadow-lg">
          <Dialog.Title className="text-lg font-semibold text-foreground">
            Create Case
          </Dialog.Title>
          <Dialog.Description className="mt-1 text-sm text-muted-foreground">
            Provide a name and optional description.
          </Dialog.Description>

          <form onSubmit={handleSubmit} className="mt-4">
            <label className="block">
              <span className="text-sm font-medium text-foreground">Name</span>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                placeholder="Case name"
              />
            </label>

            <label className="mt-3 block">
              <span className="text-sm font-medium text-foreground">
                Description
              </span>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                className="mt-1 block w-full rounded-md border border-border bg-background px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                placeholder="Optional description"
              />
            </label>

            <div className="mt-4 flex justify-end gap-2">
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="rounded-md px-3 py-2 text-sm text-muted-foreground hover:bg-accent"
                >
                  Cancel
                </button>
              </Dialog.Close>
              <button
                type="submit"
                disabled={createCase.isPending}
                className="rounded-md bg-primary px-3 py-2 text-sm text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
              >
                {createCase.isPending ? 'Creating...' : 'Create'}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
