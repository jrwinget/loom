import type { ExportBundle, ExportContents } from '@/types/export';

interface ExportContentsPanelProps {
  bundle: ExportBundle;
}

// manifest/options keys arrive verbatim (snake_case, opaque to the
// api-client transform); label them for humans here
const LAYER_LABELS: Record<string, string> = {
  assets: 'Evidence files (metadata)',
  original_files: 'Original files',
  chain_of_custody: 'Chain of custody entries',
  timeline_events: 'Timeline events',
  annotations: 'Annotations',
};

function labelFor(key: string): string {
  return LAYER_LABELS[key] ?? key.replace(/_/g, ' ');
}

function contentsOf(bundle: ExportBundle): ExportContents | null {
  const contents = bundle.manifest?.['contents'];
  if (
    contents &&
    typeof contents === 'object' &&
    'included' in contents &&
    'excluded' in contents
  ) {
    return contents as unknown as ExportContents;
  }
  return null;
}

/**
 * what a bundle actually contains — and what it deliberately does
 * not. exports are served on courts and opposing counsel; a silent
 * omission reads as a misrepresentation, so the summary is shown
 * on the row, not behind a tooltip.
 */
export function ExportContentsPanel(
  props: ExportContentsPanelProps,
): React.ReactElement | null {
  const { bundle } = props;
  const contents = contentsOf(bundle);
  const options = bundle.options;

  if (!contents && !options) return null;

  if (contents) {
    const included = Object.entries(contents.included);
    const excluded = Object.entries(contents.excluded);
    return (
      <div
        className="border-border mt-3 border-t pt-3 text-xs"
        data-testid={`export-contents-${bundle.id}`}
      >
        <p className="text-foreground font-medium">Included</p>
        <ul className="text-muted-foreground mt-0.5 space-y-0.5">
          {included.map(([key, count]) => (
            <li key={key}>
              {labelFor(key)}: {count}
            </li>
          ))}
        </ul>
        {excluded.length > 0 && (
          <>
            <p className="text-foreground mt-2 font-medium">Excluded</p>
            <ul
              className="text-muted-foreground mt-0.5 space-y-0.5"
              data-testid={`export-excluded-${bundle.id}`}
            >
              {excluded.map(([key, reason]) => (
                <li key={key}>
                  {labelFor(key)}: {reason}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    );
  }

  // formats whose builders do not write a manifest onto the record
  // (pdf report, court bundle) still show what was requested
  const requested: string[] = [];
  if (options?.['include_originals']) requested.push('original files');
  requested.push(
    options?.['include_analysis'] === false
      ? 'analysis layer excluded (evidence-only)'
      : 'analysis layer included',
  );
  return (
    <div
      className="border-border text-muted-foreground mt-3 border-t pt-3 text-xs"
      data-testid={`export-contents-${bundle.id}`}
    >
      Requested: {requested.join(', ')}
    </div>
  );
}
