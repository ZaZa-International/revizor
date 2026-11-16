/* Валидация геометрии и координат (RFC 7946, WGS84).
   Невалидные/отсутствующие координаты исключаются из карты, а не подменяются выдуманными. */

export function isFiniteNumber(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v);
}

export function isValidLongitude(v: unknown): v is number {
  return isFiniteNumber(v) && v >= -180 && v <= 180;
}

export function isValidLatitude(v: unknown): v is number {
  return isFiniteNumber(v) && v >= -90 && v <= 90;
}

export function looksSwapped(lon: unknown, lat: unknown): boolean {
  return (
    isFiniteNumber(lon) &&
    isFiniteNumber(lat) &&
    Math.abs(lat) > 90 &&
    Math.abs(lon) <= 90
  );
}

export type CoordResult =
  | { ok: true; value: [number, number] }
  | { ok: false; reason: 'invalid_geometry' | 'swapped_coordinates' };

export function validatePosition(coords: unknown): CoordResult {
  if (!Array.isArray(coords) || coords.length < 2) return { ok: false, reason: 'invalid_geometry' };
  const [lon, lat] = coords;
  if (looksSwapped(lon, lat)) return { ok: false, reason: 'swapped_coordinates' };
  if (!isValidLongitude(lon) || !isValidLatitude(lat)) return { ok: false, reason: 'invalid_geometry' };
  return { ok: true, value: [lon, lat] };
}

export function validatePointGeometry(geometry: unknown): CoordResult {
  if (!geometry || typeof geometry !== 'object') return { ok: false, reason: 'invalid_geometry' };
  const g = geometry as { type?: unknown; coordinates?: unknown };
  if (g.type !== 'Point') return { ok: false, reason: 'invalid_geometry' };
  return validatePosition(g.coordinates);
}

export function validateLineStringGeometry(
  geometry: unknown,
): { ok: true; value: [number, number][] } | { ok: false; reason: 'invalid_geometry' | 'swapped_coordinates' } {
  if (!geometry || typeof geometry !== 'object') return { ok: false, reason: 'invalid_geometry' };
  const g = geometry as { type?: unknown; coordinates?: unknown };
  if (g.type !== 'LineString' || !Array.isArray(g.coordinates) || g.coordinates.length < 2) {
    return { ok: false, reason: 'invalid_geometry' };
  }
  const out: [number, number][] = [];
  for (const pos of g.coordinates) {
    const r = validatePosition(pos);
    if (!r.ok) return { ok: false, reason: r.reason };
    out.push(r.value);
  }
  return { ok: true, value: out };
}

export function metersToDegreesLat(m: number): number {
  return m / 111_320;
}

export function metersToDegreesLon(m: number, lat: number): number {
  const cos = Math.cos((lat * Math.PI) / 180);
  return m / (111_320 * Math.max(0.01, Math.abs(cos)));
}

export function accuracyPolygon(lon: number, lat: number, radiusM: number, vertices = 48): GeoJSON.Polygon {
  const dLat = metersToDegreesLat(radiusM);
  const dLon = metersToDegreesLon(radiusM, lat);
  const ring: [number, number][] = [];
  for (let i = 0; i < vertices; i++) {
    const a = (i / vertices) * 2 * Math.PI;
    ring.push([lon + dLon * Math.cos(a), lat + dLat * Math.sin(a)]);
  }
  ring.push(ring[0]);
  return { type: 'Polygon', coordinates: [ring] };
}
