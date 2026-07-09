import { useEffect, useState } from 'react';
import { Command } from 'cmdk';
import { useNavigate } from 'react-router-dom';
import {
  useGlobalSearch,
  type GlobalSearchResult,
} from '@/hooks/use-global-search';

// where a search hit routes to. annotations have no standalone view,
// so they land on the case overview.
function resultHref(r: GlobalSearchResult): string {
  switch (r.type) {
    case 'asset':
      return `/cases/${r.caseId}/assets`;
    case 'event':
      return `/cases/${r.caseId}/timeline`;
    case 'case':
    case 'annotation':
      return `/cases/${r.caseId}`;
  }
}

const TYPE_LABEL: Record<GlobalSearchResult['type'], string> = {
  case: 'Case',
  asset: 'Asset',
  event: 'Event',
  annotation: 'Annotation',
};

const ACTIONS: { label: string; href: string }[] = [
  { label: 'Go to Dashboard', href: '/' },
  { label: 'Go to Cases', href: '/cases' },
  { label: 'Go to Settings', href: '/settings/security' },
];

export function CommandPalette(): React.ReactElement {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const navigate = useNavigate();
  const { data } = useGlobalSearch(query);
  const results = data?.results ?? [];

  // cmd+k / ctrl+k toggles the palette from anywhere
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key.toLowerCase() === 'k' && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, []);

  const go = (href: string): void => {
    setOpen(false);
    setQuery('');
    navigate(href);
  };

  return (
    <Command.Dialog
      open={open}
      onOpenChange={setOpen}
      label="Command palette"
      data-testid="command-palette"
      className="border-border bg-popover text-popover-foreground fixed top-24 left-1/2 z-50 w-full max-w-lg -translate-x-1/2 overflow-hidden rounded-lg border shadow-xl"
    >
      <Command.Input
        value={query}
        onValueChange={setQuery}
        placeholder="Search cases, assets, timeline, annotations…"
        className="border-border w-full border-b bg-transparent px-4 py-3 text-sm outline-none"
      />
      <Command.List className="max-h-80 overflow-y-auto p-1">
        {/* the actions group is always present, so cmdk's built-in
            Command.Empty never fires; drive the hint explicitly */}
        {query.trim().length >= 2 && results.length === 0 && (
          <p
            data-testid="palette-no-matches"
            className="text-muted-foreground px-3 py-4 text-sm"
          >
            {`No matches for "${query.trim()}".`}
          </p>
        )}

        {results.length > 0 && (
          <Command.Group
            heading="Results"
            className="text-muted-foreground px-2 py-1 text-xs"
          >
            {results.map((r) => (
              <Command.Item
                key={`${r.type}-${r.id}`}
                // cmdk filters on value; include the title so typing
                // narrows client-side too, but our server results are
                // already the source of truth
                value={`${r.title} ${r.id}`}
                onSelect={() => go(resultHref(r))}
                className="aria-selected:bg-accent aria-selected:text-accent-foreground flex items-center gap-2 rounded px-2 py-2 text-sm"
              >
                <span className="bg-muted text-muted-foreground rounded px-1.5 py-0.5 text-xs">
                  {TYPE_LABEL[r.type]}
                </span>
                <span className="truncate">{r.title}</span>
              </Command.Item>
            ))}
          </Command.Group>
        )}

        <Command.Group
          heading="Actions"
          className="text-muted-foreground px-2 py-1 text-xs"
        >
          {ACTIONS.map((a) => (
            <Command.Item
              key={a.href}
              value={a.label}
              onSelect={() => go(a.href)}
              className="aria-selected:bg-accent aria-selected:text-accent-foreground rounded px-2 py-2 text-sm"
            >
              {a.label}
            </Command.Item>
          ))}
        </Command.Group>
      </Command.List>
    </Command.Dialog>
  );
}
