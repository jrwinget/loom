import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { CaseMap } from '@/components/map/case-map';

// mock react-leaflet to avoid jsdom issues
vi.mock('react-leaflet', () => ({
  MapContainer: ({
    children,
  }: {
    children: React.ReactNode;
  }) => <div data-testid="mock-map-container">{children}</div>,
  TileLayer: () => <div data-testid="mock-tile-layer" />,
  Marker: ({
    children,
  }: {
    children: React.ReactNode;
  }) => <div data-testid="mock-marker">{children}</div>,
  Popup: ({
    children,
  }: {
    children: React.ReactNode;
  }) => <div>{children}</div>,
  useMap: () => ({
    fitBounds: vi.fn(),
  }),
}));

// mock the geo hooks
vi.mock('@/hooks/use-geo', () => ({
  useGeoAssets: vi.fn(),
  useGeoEvents: vi.fn(),
  useGeoBounds: vi.fn(),
}));

import {
  useGeoAssets,
  useGeoEvents,
  useGeoBounds,
} from '@/hooks/use-geo';

const mockUseGeoAssets = vi.mocked(useGeoAssets);
const mockUseGeoEvents = vi.mocked(useGeoEvents);
const mockUseGeoBounds = vi.mocked(useGeoBounds);

function renderWithProviders(ui: React.ReactElement): void {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

// helper to create mock query result
function mockQueryResult<T>(data: T | undefined): ReturnType<typeof useGeoAssets> {
  return {
    data,
    isLoading: false,
    isError: false,
    error: null,
    status: 'success',
    fetchStatus: 'idle',
  } as ReturnType<typeof useGeoAssets>;
}

describe('CaseMap', () => {
  it('renders map container with markers', () => {
    mockUseGeoAssets.mockReturnValue(
      mockQueryResult({
        items: [
          {
            id: 'a1',
            originalFilename: 'photo.jpg',
            contentType: 'image/jpeg',
            lat: 40.7,
            lon: -74.0,
            captureTime: '2026-01-15T10:00:00Z',
          },
        ],
      }) as ReturnType<typeof useGeoAssets>,
    );
    mockUseGeoEvents.mockReturnValue(
      mockQueryResult({ items: [] }) as ReturnType<typeof useGeoEvents>,
    );
    mockUseGeoBounds.mockReturnValue(
      mockQueryResult({
        minLat: 40.0,
        maxLat: 41.0,
        minLon: -75.0,
        maxLon: -73.0,
        timeStart: '2026-01-15T00:00:00Z',
        timeEnd: '2026-01-15T23:59:59Z',
      }) as ReturnType<typeof useGeoBounds>,
    );

    renderWithProviders(<CaseMap caseId="case-1" />);

    expect(
      screen.getByTestId('case-map'),
    ).toBeInTheDocument();
    expect(
      screen.getByTestId('mock-map-container'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('photo.jpg'),
    ).toBeInTheDocument();
  });

  it('shows empty state when no geotagged items', () => {
    mockUseGeoAssets.mockReturnValue(
      mockQueryResult({ items: [] }) as ReturnType<typeof useGeoAssets>,
    );
    mockUseGeoEvents.mockReturnValue(
      mockQueryResult({ items: [] }) as ReturnType<typeof useGeoEvents>,
    );
    mockUseGeoBounds.mockReturnValue(
      mockQueryResult(undefined) as ReturnType<typeof useGeoBounds>,
    );

    renderWithProviders(<CaseMap caseId="case-1" />);

    expect(
      screen.getByTestId('map-empty'),
    ).toBeInTheDocument();
    expect(
      screen.getByText('No geotagged assets'),
    ).toBeInTheDocument();
  });
});
