export interface GeoAsset {
  id: string;
  originalFilename: string;
  contentType: string;
  lat: number;
  lon: number;
  captureTime: string | null;
}

export interface GeoEvent {
  id: string;
  title: string;
  status: string;
  lat: number;
  lon: number;
  eventTimeStart: string;
  eventTimeEnd: string | null;
  hasContradictions: boolean;
}

export interface GeoBounds {
  minLat: number;
  maxLat: number;
  minLon: number;
  maxLon: number;
  timeStart: string | null;
  timeEnd: string | null;
}
