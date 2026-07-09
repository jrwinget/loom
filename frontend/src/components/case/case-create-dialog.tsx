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
        <Dialog.Content className="border-border bg-card fixed top-1/2 left-1/2 w-full max-w-md -translate-x-1/2 -translate-y-1/2 rounded-lg border p-6 shadow-lg">
          <Dialog.Title className="text-foreground text-lg font-semibold">
            Create Case
          </Dialog.Title>
          <Dialog.Description className="text-muted-foreground mt-1 text-sm">
            Provide a name and optional description.
          </Dialog.Description>

          <form onSubmit={handleSubmit} className="mt-4">
            <label className="block">
              <span className="text-foreground text-sm font-medium">Name</span>
              <input
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="border-border bg-background text-foreground placeholder:text-muted-foreground focus:ring-ring mt-1 block w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:outline-hidden"
                placeholder="Case name"
              />
            </label>

            <label className="mt-3 block">
              <span className="text-foreground text-sm font-medium">
                Description
              </span>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
                className="border-border bg-background text-foreground placeholder:text-muted-foreground focus:ring-ring mt-1 block w-full rounded-md border px-3 py-2 text-sm focus:ring-2 focus:outline-hidden"
                placeholder="Optional description"
              />
            </label>

            <div className="mt-4 flex justify-end gap-2">
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="text-muted-foreground hover:bg-accent rounded-md px-3 py-2 text-sm"
                >
                  Cancel
                </button>
              </Dialog.Close>
              <button
                type="submit"
                disabled={createCase.isPending}
                className="bg-primary text-primary-foreground hover:bg-primary/90 rounded-md px-3 py-2 text-sm disabled:opacity-50"
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
