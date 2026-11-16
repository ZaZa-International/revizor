/* Geospatial data adapter: API FeatureCollection → внутренние GeoFeature → render GeoJSON.
   Domain-свойства (id, severity, confidence, …) сохраняются без изменений;
   визуальные значения добавляются отдельными полями с префиксом `_`. */

import type {
  AssetMapCollection,
  DefectMapCollection,
  ObservationMapCollection,
  RouteMapCollection,
} from '../api/types';
import { BAND_COLORS, DEFECT_RING_SEVERITY_MIN, GEO_COLORS } from './palette';
import type { AdaptedLayer, GeoFeature, GeoKind, RejectedFeature } from './types';
import { accuracyPolygon, validateLineStringGeometry, validatePointGeometry } from './validate';

export type MapCollection =
  | AssetMapCollection
  | DefectMapCollection
  | ObservationMapCollection
  | RouteMapCollection;

const EMPTY: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] };

function presentationFor(kind: GeoKind, domain: Record<string, unknown>): GeoFeature['presentation'] {
  const label = String(
    domain.display_name ?? domain.name ?? domain.defect_type ?? domain.object_type ?? 'Объект',
  );
  switch (kind) {
    case 'assets': {
      const band = String(domain.priority_band ?? 'NEEDS_REVIEW');
      return { color: BAND_COLORS[band] ?? BAND_COLORS.NEEDS_REVIEW, ringColor: null, label };
    }
    case 'observations':
      return {
        color: domain.review_status === 'UNREVIEWED' ? GEO_COLORS.warn : GEO_COLORS.accent,
        ringColor: null,
        label,
      };
    case 'defects': {
      const severity = Number(domain.severity ?? 0);
      return {
        color: 'rgba(0,0,0,0)',
        ringColor: severity >= DEFECT_RING_SEVERITY_MIN ? GEO_COLORS.crit : GEO_COLORS.warn,
        label,
      };
    }
    case 'routes':
      return { color: GEO_COLORS.accentDim, ringColor: null, label };
  }
}

export function adaptCollection(kind: GeoKind, collection: MapCollection | null | undefined): AdaptedLayer {
  const features: GeoFeature[] = [];
  const rejected: RejectedFeature[] = [];
  const renderFeatures: GeoJSON.Feature[] = [];

  for (const f of collection?.features ?? []) {
    const domain = (f.properties ?? {}) as Record<string, unknown>;
    const id = domain.id != null ? String(domain.id) : null;
    const geometry = f.geometry;

    if (!geometry) {
      rejected.push({ kind, id, reason: 'missing_geometry' });
      continue;
    }

    let normalized: GeoJSON.Point | GeoJSON.LineString;
    if (geometry.type === 'Point') {
      const r = validatePointGeometry(geometry);
      if (!r.ok) {
        rejected.push({ kind, id, reason: r.reason });
        continue;
      }
      normalized = { type: 'Point', coordinates: r.value };
    } else if (geometry.type === 'LineString') {
      const r = validateLineStringGeometry(geometry);
      if (!r.ok) {
        rejected.push({ kind, id, reason: r.reason });
        continue;
      }
      normalized = { type: 'LineString', coordinates: r.value };
    } else {
      rejected.push({ kind, id, reason: 'unsupported_type' });
      continue;
    }

    const presentation = presentationFor(kind, domain);
    features.push({ kind, id: id ?? '', geometry: normalized, domain, presentation });
    renderFeatures.push({
      type: 'Feature',
      id: id ?? undefined,
      geometry: normalized,
      properties: {
        ...domain,
        _kind: kind,
        _color: presentation.color,
        _ring: presentation.ringColor,
        _label: presentation.label,
      },
    });
  }

  return { features, rejected, render: { type: 'FeatureCollection', features: renderFeatures } };
}

export function emptyCollection(): GeoJSON.FeatureCollection {
  return EMPTY;
}

export function findFeature(layers: AdaptedLayer[], id: string | null | undefined): GeoFeature | null {
  if (!id) return null;
  for (const layer of layers) {
    const f = layer.features.find((x) => x.id === id);
    if (f) return f;
  }
  return null;
}

export function featurePosition(f: GeoFeature): [number, number] | null {
  if (f.geometry.type === 'Point') return f.geometry.coordinates as [number, number];
  const coords = f.geometry.coordinates;
  if (coords.length === 0) return null;
  const mid = coords[Math.floor(coords.length / 2)];
  return [mid[0], mid[1]];
}

export function boundsOf(layers: AdaptedLayer[]): [[number, number], [number, number]] | null {
  let minLon = Infinity;
  let minLat = Infinity;
  let maxLon = -Infinity;
  let maxLat = -Infinity;
  let count = 0;
  const push = (lon: number, lat: number) => {
    count++;
    if (lon < minLon) minLon = lon;
    if (lat < minLat) minLat = lat;
    if (lon > maxLon) maxLon = lon;
    if (lat > maxLat) maxLat = lat;
  };
  for (const layer of layers) {
    for (const f of layer.features) {
      if (f.geometry.type === 'Point') push(f.geometry.coordinates[0], f.geometry.coordinates[1]);
      else f.geometry.coordinates.forEach((c) => push(c[0], c[1]));
    }
  }
  if (count === 0) return null;
  return [
    [minLon, minLat],
    [maxLon, maxLat],
  ];
}

export function selectionCollection(f: GeoFeature | null): GeoJSON.FeatureCollection {
  if (!f) return EMPTY;
  const pos = featurePosition(f);
  if (!pos) return EMPTY;
  return {
    type: 'FeatureCollection',
    features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: pos }, properties: {} }],
  };
}

/* Кольца неопределённости геоположения: только реальный location_accuracy_m
   для ESTIMATED-точек. CONFIRMED без accuracy и UNAVAILABLE не рисуются. */
export function accuracyCollection(layers: AdaptedLayer[]): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = [];
  for (const layer of layers) {
    for (const f of layer.features) {
      if (f.geometry.type !== 'Point') continue;
      if (f.domain.geolocation_status !== 'ESTIMATED') continue;
      const radius = Number(f.domain.location_accuracy_m ?? 0);
      if (!Number.isFinite(radius) || radius <= 0) continue;
      const [lon, lat] = f.geometry.coordinates;
      features.push({
        type: 'Feature',
        properties: { id: f.id, accuracy_m: radius },
        geometry: accuracyPolygon(lon, lat, radius),
      });
    }
  }
  return { type: 'FeatureCollection', features };
}
