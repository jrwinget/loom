import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { ExportContentsPanel } from '@/components/export/export-contents-panel';
import type { ExportBundle } from '@/types/export';

function makeBundle(overrides: Partial<ExportBundle>): ExportBundle {
  return {
    id: 'e1',
    caseId: 'c1',
    name: 'Production Set',
    format: 'zip',
    storageKey: 'exports/e1/bundle.zip',
    sha256Hash: 'a'.repeat(64),
    downloadUrl: null,
    status: 'complete',
    manifest: null,
    options: null,
    createdBy: 'u1',
    createdAt: '2026-07-24T12:00:00Z',
    ...overrides,
  };
}

describe('ExportContentsPanel', () => {
  it('renders nothing when neither manifest nor options exist', () => {
    const { container } = render(
      <ExportContentsPanel bundle={makeBundle({})} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('lists included counts and excluded reasons from the manifest', () => {
    const bundle = makeBundle({
      manifest: {
        contents: {
          included: { assets: 3, chain_of_custody: 9 },
          excluded: {
            timeline_events:
              'analysis layer excluded (attorney work product)',
            original_files: 'not requested',
          },
        },
      },
    });
    render(<ExportContentsPanel bundle={bundle} />);

    expect(screen.getByTestId('export-contents-e1')).toBeInTheDocument();
    expect(
      screen.getByText('Evidence files (metadata): 3'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('Chain of custody entries: 9'),
    ).toBeInTheDocument();
    const excluded = screen.getByTestId('export-excluded-e1');
    expect(excluded).toHaveTextContent(
      'Timeline events: analysis layer excluded (attorney work product)',
    );
    expect(excluded).toHaveTextContent('Original files: not requested');
  });

  it('omits the excluded block when nothing was excluded', () => {
    const bundle = makeBundle({
      manifest: {
        contents: {
          included: { assets: 1 },
          excluded: {},
        },
      },
    });
    render(<ExportContentsPanel bundle={bundle} />);
    expect(
      screen.queryByTestId('export-excluded-e1'),
    ).not.toBeInTheDocument();
  });

  it('falls back to the requested options when no manifest exists', () => {
    const bundle = makeBundle({
      format: 'court_bundle',
      options: { include_originals: true, include_analysis: false },
    });
    render(<ExportContentsPanel bundle={bundle} />);
    const panel = screen.getByTestId('export-contents-e1');
    expect(panel).toHaveTextContent('Requested: original files');
    expect(panel).toHaveTextContent(
      'analysis layer excluded (evidence-only)',
    );
  });
});
