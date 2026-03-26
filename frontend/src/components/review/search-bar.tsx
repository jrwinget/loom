import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from 'react';
import { useSearch } from '@/hooks/use-search';
import { useKeyboardShortcut } from '@/hooks/use-keyboard';
import type { SearchResult } from '@/types/transcript';

interface SearchBarProps {
  caseId: string;
  onResultClick?: (result: SearchResult) => void;
}

const typeLabels: Record<string, string> = {
  transcript: 'Transcripts',
  ocr: 'OCR',
  annotation: 'Annotations',
  event: 'Events',
  asset: 'Assets',
};

const typeOrder = [
  'transcript',
  'ocr',
  'annotation',
  'event',
  'asset',
];

export function SearchBar(
  props: SearchBarProps,
): React.ReactElement {
  const { caseId, onResultClick } = props;
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<
    string | null
  >(null);

  const { data } = useSearch(caseId, query);

  // group results by type
  const grouped = new Map<string, SearchResult[]>();
  if (data?.results) {
    for (const r of data.results) {
      const list = grouped.get(r.type) ?? [];
      list.push(r);
      grouped.set(r.type, list);
    }
  }

  const availableTypes = typeOrder.filter(
    (t) => grouped.has(t),
  );

  // reset active tab when results change
  useEffect(() => {
    if (availableTypes.length > 0 && !activeTab) {
      setActiveTab(availableTypes[0]);
    } else if (
      activeTab &&
      !availableTypes.includes(activeTab)
    ) {
      setActiveTab(availableTypes[0] ?? null);
    }
  }, [availableTypes, activeTab]);

  // cmd/ctrl+k to focus
  useKeyboardShortcut(
    'ctrl+k,command+k',
    () => {
      inputRef.current?.focus();
      setOpen(true);
    },
    [],
  );

  // escape to close
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Escape') {
        setOpen(false);
        inputRef.current?.blur();
      }
    },
    [],
  );

  const handleResultClick = useCallback(
    (result: SearchResult) => {
      onResultClick?.(result);
      setOpen(false);
      setQuery('');
    },
    [onResultClick],
  );

  // highlight matching text in snippet
  function highlightMatch(
    text: string,
    q: string,
  ): React.ReactElement {
    if (!q.trim()) {
      return <span>{text}</span>;
    }
    const idx = text
      .toLowerCase()
      .indexOf(q.toLowerCase());
    if (idx === -1) {
      return <span>{text}</span>;
    }
    return (
      <span>
        {text.slice(0, idx)}
        <mark
          className="bg-yellow-200
            dark:bg-yellow-800"
        >
          {text.slice(idx, idx + q.length)}
        </mark>
        {text.slice(idx + q.length)}
      </span>
    );
  }

  return (
    <div
      data-testid="search-bar"
      className="relative w-full max-w-xl"
    >
      <div className="relative">
        <span
          className="pointer-events-none absolute
            left-2 top-1/2 -translate-y-1/2
            text-muted-foreground"
          aria-hidden="true"
        >
          &#x1F50D;
        </span>
        <input
          ref={inputRef}
          data-testid="search-input"
          type="text"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder="Search (Ctrl+K)"
          className="w-full rounded border border-border
            bg-card py-1.5 pl-8 pr-3 text-sm
            text-foreground placeholder:text-muted-foreground
            focus:outline-none focus:ring-2
            focus:ring-primary/50"
        />
      </div>

      {/* results dropdown */}
      {open && query.trim().length >= 2 && (
        <div
          data-testid="search-results"
          className="absolute left-0 right-0 top-full
            z-50 mt-1 max-h-80 overflow-y-auto
            rounded border border-border bg-card
            shadow-lg"
        >
          {/* type tabs */}
          {availableTypes.length > 0 && (
            <div
              className="flex border-b border-border"
            >
              {availableTypes.map((t) => (
                <button
                  key={t}
                  type="button"
                  data-testid={`search-tab-${t}`}
                  onClick={() => setActiveTab(t)}
                  className={`px-3 py-1.5 text-xs
                    font-medium transition-colors ${
                      activeTab === t
                        ? 'border-b-2 border-primary' +
                          ' text-foreground'
                        : 'text-muted-foreground' +
                          ' hover:text-foreground'
                    }`}
                >
                  {typeLabels[t] ?? t}
                  <span
                    className="ml-1
                      text-muted-foreground"
                  >
                    {grouped.get(t)?.length ?? 0}
                  </span>
                </button>
              ))}
            </div>
          )}

          {/* result items */}
          {activeTab &&
            grouped.get(activeTab)?.map((r) => (
              <button
                key={r.id}
                type="button"
                data-testid={`search-result-${r.id}`}
                onClick={() => handleResultClick(r)}
                className="flex w-full items-start
                  gap-2 px-3 py-2 text-left
                  transition-colors hover:bg-accent/30"
              >
                <span
                  className="mt-0.5 text-xs font-medium
                    text-muted-foreground"
                >
                  {r.type}
                </span>
                <span className="text-sm text-foreground">
                  {highlightMatch(r.text, query)}
                </span>
              </button>
            ))}

          {availableTypes.length === 0 && (
            <p
              className="p-3 text-sm
                text-muted-foreground"
            >
              No results found
            </p>
          )}
        </div>
      )}
    </div>
  );
}
