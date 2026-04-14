import { useEffect, useMemo } from 'react';
import { MapContainer, TileLayer, Marker, Popup, useMap } from 'react-leaflet';
import type { LatLngBoundsExpression } from 'leaflet';
import { Link } from 'react-router-dom';
import { useGeoAssets, useGeoEvents, useGeoBounds } from '@/hooks/use-geo';

interface CaseMapProps {
  caseId: string;
  timeStart?: string;
  timeEnd?: string;
}

// child component to auto-fit bounds
function FitBounds(props: {
  bounds: LatLngBoundsExpression | null;
}): React.ReactElement | null {
  const { bounds } = props;
  const map = useMap();

  useEffect(() => {
    if (bounds) {
      map.fitBounds(bounds, { padding: [40, 40] });
    }
  }, [map, bounds]);

  return null;
}

export function CaseMap(props: CaseMapProps): React.ReactElement {
  const { caseId, timeStart, timeEnd } = props;

  const { data: assetsData } = useGeoAssets(caseId, timeStart, timeEnd);
  const { data: eventsData } = useGeoEvents(caseId, timeStart, timeEnd);
  const { data: boundsData } = useGeoBounds(caseId);

  const assets = assetsData?.items ?? [];
  const events = eventsData?.items ?? [];

  const bounds = useMemo<LatLngBoundsExpression | null>(() => {
    if (!boundsData) return null;
    return [
      [boundsData.minLat, boundsData.minLon],
      [boundsData.maxLat, boundsData.maxLon],
    ];
  }, [boundsData]);

  const hasItems = assets.length > 0 || events.length > 0;

  if (!hasItems) {
    return (
      <div
        data-testid="map-empty"
        className="flex h-full items-center justify-center rounded-lg border border-dashed border-border"
      >
        <p className="text-sm text-muted-foreground">No geotagged assets</p>
      </div>
    );
  }

  return (
    <div data-testid="case-map" className="h-full w-full">
      <MapContainer
        center={[0, 0]}
        zoom={2}
        className="h-full w-full rounded-lg"
        scrollWheelZoom
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitBounds bounds={bounds} />

        {/* asset markers (blue) */}
        {assets.map((asset) => (
          <Marker key={`asset-${asset.id}`} position={[asset.lat, asset.lon]}>
            <Popup>
              <div className="text-sm">
                <p className="font-medium">{asset.originalFilename}</p>
                <p className="text-xs text-gray-500">{asset.contentType}</p>
                <Link
                  to={`/cases/${caseId}/review/${asset.id}`}
                  className="text-xs text-blue-600 hover:underline"
                >
                  View asset
                </Link>
              </div>
            </Popup>
          </Marker>
        ))}

        {/* event markers */}
        {events.map((event) => (
          <Marker key={`event-${event.id}`} position={[event.lat, event.lon]}>
            <Popup>
              <div className="text-sm">
                <p className="font-medium">{event.title}</p>
                <p className="text-xs text-gray-500">
                  {event.status}
                  {event.hasContradictions && (
                    <span className="ml-1 text-amber-600">
                      (contradictions)
                    </span>
                  )}
                </p>
                <Link
                  to={`/cases/${caseId}/timeline`}
                  className="text-xs text-blue-600 hover:underline"
                >
                  View on timeline
                </Link>
              </div>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
