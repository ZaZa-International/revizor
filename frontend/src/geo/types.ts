/* Единые внутренние типы геоданных. Координаты строго RFC 7946: [longitude, latitude], WGS84.
   Высота в данных Revizor отсутствует — третья координата не интерпретируется как altitude. */

export type Longitude = number & { readonly __brand: 'Longitude' };
export type Latitude = number & { readonly __brand: 'Latitude' };

export interface LngLat {
  lon: Longitude;
  lat: Latitude;
}

export type GeoKind = 'assets' | 'defects' | 'observations' | 'routes';

export type ValidGeometry = GeoJSON.Point | GeoJSON.LineString;

export interface GeoFeature {
  kind: GeoKind;
  id: string;
  geometry: ValidGeometry;
  domain: Record<string, unknown>;
  presentation: FeaturePresentation;
}

export interface FeaturePresentation {
  color: string;
  ringColor: string | null;
  label: string;
}

export interface RejectedFeature {
  kind: GeoKind;
  id: string | null;
  reason: 'missing_geometry' | 'invalid_geometry' | 'unsupported_type' | 'swapped_coordinates';
}

export interface AdaptedLayer {
  features: GeoFeature[];
  rejected: RejectedFeature[];
  render: GeoJSON.FeatureCollection;
}

export interface MapCamera {
  center: [number, number];
  zoom: number;
  pitch: number;
  bearing: number;
}

export type MapMode = '2d' | '3d';

export function lngLat(lon: number, lat: number): LngLat {
  return { lon: lon as Longitude, lat: lat as Latitude };
}

export function toArray(p: LngLat): [number, number] {
  return [p.lon, p.lat];
}
