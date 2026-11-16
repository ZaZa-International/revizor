/* Геопривязка сетки покрытия /analytics/coverage.
   Формула ячеек повторяет backend (application/services/analytics.py:132-141):
   equirectangular approximation, cell_lon по mid_lat bbox. Данные реальные, не выдуманные. */

import type { CoverageResponse } from '../api/types';
import { metersToDegreesLat, metersToDegreesLon } from './validate';

export interface CoverageGrid {
  cellLat: number;
  cellLon: number;
  minLon: number;
  minLat: number;
}

export function coverageGrid(c: CoverageResponse): CoverageGrid {
  const { min_longitude, min_latitude, max_latitude } = c.area_bbox;
  const midLat = (min_latitude + max_latitude) / 2;
  return {
    cellLat: metersToDegreesLat(c.grid_cell_m),
    cellLon: metersToDegreesLon(c.grid_cell_m, midLat),
    minLon: min_longitude,
    minLat: min_latitude,
  };
}

export function coverageCells(c: CoverageResponse | null | undefined): GeoJSON.FeatureCollection {
  if (!c) return { type: 'FeatureCollection', features: [] };
  const g = coverageGrid(c);
  const features: GeoJSON.Feature[] = c.covered_cell_counts.map((cell) => {
    const x0 = g.minLon + cell.cx * g.cellLon;
    const y0 = g.minLat + cell.cy * g.cellLat;
    const x1 = x0 + g.cellLon;
    const y1 = y0 + g.cellLat;
    return {
      type: 'Feature',
      properties: { cx: cell.cx, cy: cell.cy, observations: cell.observations },
      geometry: {
        type: 'Polygon',
        coordinates: [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]],
      },
    };
  });
  return { type: 'FeatureCollection', features };
}

export function coverageAreaOutline(c: CoverageResponse | null | undefined): GeoJSON.FeatureCollection {
  if (!c) return { type: 'FeatureCollection', features: [] };
  const b = c.area_bbox;
  return {
    type: 'FeatureCollection',
    features: [
      {
        type: 'Feature',
        properties: { coverage_ratio: c.coverage_ratio, covered_cells: c.covered_cells, gap_cells: c.gap_cells },
        geometry: {
          type: 'Polygon',
          coordinates: [[
            [b.min_longitude, b.min_latitude],
            [b.max_longitude, b.min_latitude],
            [b.max_longitude, b.max_latitude],
            [b.min_longitude, b.max_latitude],
            [b.min_longitude, b.min_latitude],
          ]],
        },
      },
    ],
  };
}
