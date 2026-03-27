import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ProvenancePanel } from '@/components/asset/provenance-panel';
import type { ProvenanceListResponse } from '@/types/provenance';

const mockRecords: ProvenanceListResponse = {
  items: [
    {
      id: 'prov-1',
      assetId: 'asset-1',
      exportId: null,
      manifestData: {
        claim_generator: 'Loom/0.1.0',
        title: 'test.jpg',
      },
      claimGenerator: 'Loom/0.1.0',
      actions: [
        { action: 'uploaded', when: '2025-01-01T00:00:00Z' },
        { action: 'c2pa.exported', when: '2025-01-02T00:00:00Z' },
      ],
      createdAt: '2025-01-01T00:00:00Z',
    },
  ],
  total: 1,
};

const emptyRecords: ProvenanceListResponse = {
  items: [],
  total: 0,
};

vi.mock('@/hooks/use-provenance', () => ({
  useAssetProvenance: vi.fn(),
}));

// eslint-disable-next-line @typescript-eslint/no-require-imports
import { useAssetProvenance } from '@/hooks/use-provenance';
const mockUseAssetProvenance = vi.mocked(useAssetProvenance);

function renderPanel(): ReturnType<typeof render> {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ProvenancePanel caseId="case-1" assetId="asset-1" />
    </QueryClientProvider>,
  );
}

describe('ProvenancePanel', () => {
  it('renders provenance records', () => {
    mockUseAssetProvenance.mockReturnValue({
      data: mockRecords,
      isLoading: false,
    } as ReturnType<typeof useAssetProvenance>);

    renderPanel();

    expect(screen.getByTestId('provenance-panel')).toBeInTheDocument();
    expect(screen.getByText('Loom/0.1.0')).toBeInTheDocument();
    expect(screen.getAllByTestId('action-item')).toHaveLength(2);
    expect(screen.getByText('uploaded')).toBeInTheDocument();
    expect(screen.getByText('c2pa.exported')).toBeInTheDocument();
  });

  it('shows empty state', () => {
    mockUseAssetProvenance.mockReturnValue({
      data: emptyRecords,
      isLoading: false,
    } as ReturnType<typeof useAssetProvenance>);

    renderPanel();

    expect(screen.getByTestId('provenance-empty')).toBeInTheDocument();
    expect(screen.getByText('No provenance data yet')).toBeInTheDocument();
  });

  it('expandable manifest data', () => {
    mockUseAssetProvenance.mockReturnValue({
      data: mockRecords,
      isLoading: false,
    } as ReturnType<typeof useAssetProvenance>);

    renderPanel();

    // manifest json should not be visible initially
    expect(screen.queryByTestId('manifest-json')).not.toBeInTheDocument();

    // click to expand
    fireEvent.click(screen.getByTestId('toggle-manifest'));

    // manifest json should now be visible
    expect(screen.getByTestId('manifest-json')).toBeInTheDocument();
    expect(screen.getByTestId('manifest-json').textContent).toContain(
      'Loom/0.1.0',
    );

    // click again to collapse
    fireEvent.click(screen.getByTestId('toggle-manifest'));
    expect(screen.queryByTestId('manifest-json')).not.toBeInTheDocument();
  });
});
