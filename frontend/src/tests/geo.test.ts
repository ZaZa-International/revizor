import { describe, expect, it } from 'vitest';
import {
  accuracyCollection,
  adaptCollection,
  boundsOf,
  featurePosition,
  findFeature,
  selectionCollection,
} from '../geo/adapter';
import { coverageCells, coverageGrid } from '../geo/coverage';
import {
  defaultLayers,
  parseCamera,
  parseMapState,
  serializeCamera,
  serializeMapState,
} from '../geo/state';
import {
  accuracyPolygon,
  looksSwapped,
  validateLineStringGeometry,
  validatePointGeometry,
  validatePosition,
} from '../geo/validate';
import type { AssetMapCollection, DefectMapCollection } from '../api/types';

const assetFC = (features: unknown[]): AssetMapCollection =>
  ({ type: 'FeatureCollection', features }) as AssetMapCollection;

const point = (id: string, lon: number, lat: number, extra: Record<string, unknown> = {}) => ({
  type: 'Feature',
  geometry: { type: 'Point', coordinates: [lon, lat] },
  properties: { id, asset_type: 'telecom_well', priority_band: 'HIGH_PRIORITY', ...extra },
});

describe('геоадаптер: валидация координат (RFC 7946, WGS84)', () => {
  it('порядок [lon, lat] сохраняется', () => {
    const r = validatePosition([37.6173, 55.7558]);
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.value).toEqual([37.6173, 55.7558]);
  });

  it('swap-эвристика: |lat|>90 при |lon|<=90', () => {
    expect(looksSwapped(55.7558, 37.6173)).toBe(false);
    expect(looksSwapped(37.6173, 155.7558)).toBe(true);
    const r = validatePosition([37.6173, 155.7558]);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.reason).toBe('swapped_coordinates');
  });

  it('выход за диапазоны отклоняется', () => {
    expect(validatePosition([181, 55]).ok).toBe(false);
    expect(validatePosition([37, -91]).ok).toBe(false);
    expect(validatePosition([NaN, 55]).ok).toBe(false);
    expect(validatePosition([37]).ok).toBe(false);
    expect(validatePosition(null).ok).toBe(false);
  });

  it('третья координата не интерпретируется как высота и не ломает точку', () => {
    const r = validatePointGeometry({ type: 'Point', coordinates: [37.6, 55.7, 120] });
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.value).toEqual([37.6, 55.7]);
  });

  it('LineString требует >=2 валидных точек', () => {
    expect(validateLineStringGeometry({ type: 'LineString', coordinates: [[37, 55]] }).ok).toBe(false);
    expect(
      validateLineStringGeometry({ type: 'LineString', coordinates: [[37, 55], [37.1, 55.1]] }).ok,
    ).toBe(true);
    expect(
      validateLineStringGeometry({ type: 'LineString', coordinates: [[37, 55], [999, 55]] }).ok,
    ).toBe(false);
  });
});

describe('геоадаптер: нормализация API → внутренние типы', () => {
  it('сохраняет исходные id и domain-свойства без подмены', () => {
    const fc = assetFC([point('a1', 37.6, 55.7, { current_priority: 88, display_name: 'Колодец' })]);
    const layer = adaptCollection('assets', fc);
    expect(layer.features).toHaveLength(1);
    expect(layer.features[0].id).toBe('a1');
    expect(layer.features[0].domain.current_priority).toBe(88);
    expect(layer.features[0].domain.display_name).toBe('Колодец');
    const renderProps = layer.render.features[0].properties as Record<string, unknown>;
    expect(renderProps.current_priority).toBe(88);
    expect(renderProps._color).toBe('#E66C61');
    expect(renderProps._kind).toBe('assets');
  });

  it('отсутствующая геометрия исключается, а не ставится в центр карты', () => {
    const fc = assetFC([
      { type: 'Feature', geometry: null, properties: { id: 'no-gps' } },
      point('ok', 37.6, 55.7),
    ]);
    const layer = adaptCollection('assets', fc);
    expect(layer.features).toHaveLength(1);
    expect(layer.rejected).toEqual([{ kind: 'assets', id: 'no-gps', reason: 'missing_geometry' }]);
  });

  it('невалидная и неподдерживаемая геометрия отклоняется с причиной', () => {
    const fc = assetFC([
      { type: 'Feature', geometry: { type: 'Point', coordinates: [181, 55] }, properties: { id: 'bad' } },
      { type: 'Feature', geometry: { type: 'Polygon', coordinates: [] }, properties: { id: 'poly' } },
    ]);
    const layer = adaptCollection('assets', fc);
    expect(layer.features).toHaveLength(0);
    expect(layer.rejected.map((r) => r.reason)).toEqual(['invalid_geometry', 'unsupported_type']);
  });

  it('презентация дефектов: кольцо S4+ красное, S1–3 янтарное', () => {
    const fc = {
      type: 'FeatureCollection',
      features: [
        { type: 'Feature', geometry: { type: 'Point', coordinates: [37.6, 55.7] }, properties: { id: 'd4', severity: 4 } },
        { type: 'Feature', geometry: { type: 'Point', coordinates: [37.6, 55.7] }, properties: { id: 'd3', severity: 3 } },
      ],
    } as DefectMapCollection;
    const layer = adaptCollection('defects', fc);
    expect(layer.features[0].presentation.ringColor).toBe('#E66C61');
    expect(layer.features[1].presentation.ringColor).toBe('#F0A45C');
  });

  it('null-коллекция даёт пустой слой без ошибок', () => {
    const layer = adaptCollection('assets', null);
    expect(layer.features).toHaveLength(0);
    expect(layer.render.features).toHaveLength(0);
  });

  it('boundsOf и selectionCollection работают по реальным координатам', () => {
    const layer = adaptCollection('assets', assetFC([point('a', 37.6, 55.7), point('b', 37.7, 55.8)]));
    expect(boundsOf([layer])).toEqual([[37.6, 55.7], [37.7, 55.8]]);
    const f = findFeature([layer], 'b');
    expect(f?.id).toBe('b');
    const sel = selectionCollection(f);
    expect(sel.features[0].geometry).toEqual({ type: 'Point', coordinates: [37.7, 55.8] });
    expect(selectionCollection(null).features).toHaveLength(0);
  });

  it('featurePosition для LineString — середина трека', () => {
    const layer = adaptCollection('routes', {
      type: 'FeatureCollection',
      features: [
        {
          type: 'Feature',
          geometry: { type: 'LineString', coordinates: [[37.6, 55.7], [37.62, 55.72], [37.64, 55.74]] },
          properties: { id: 'r1', name: 'Трек' },
        },
      ],
    } as never);
    expect(featurePosition(layer.features[0])).toEqual([37.62, 55.72]);
  });
});

describe('кольца неопределённости GPS', () => {
  it('рисуются только для ESTIMATED с положительной точностью', () => {
    const layer = adaptCollection(
      'assets',
      assetFC([
        point('est', 37.6, 55.7, { geolocation_status: 'ESTIMATED', location_accuracy_m: 25 }),
        point('conf', 37.6, 55.7, { geolocation_status: 'CONFIRMED', location_accuracy_m: 4 }),
        point('noacc', 37.6, 55.7, { geolocation_status: 'ESTIMATED', location_accuracy_m: null }),
      ]),
    );
    const acc = accuracyCollection([layer]);
    expect(acc.features).toHaveLength(1);
    expect(acc.features[0].properties?.accuracy_m).toBe(25);
  });

  it('радиус полигона соответствует метрам (широта)', () => {
    const poly = accuracyPolygon(37.6, 55.7, 111_320, 48);
    const ring = poly.coordinates[0];
    const maxLat = Math.max(...ring.map((c) => c[1]));
    expect(maxLat - 55.7).toBeCloseTo(1, 2);
  });
});

describe('покрытие: геопривязка сетки /analytics/coverage', () => {
  const coverage = {
    area_bbox: { min_longitude: 37.55, min_latitude: 55.7, max_longitude: 37.7, max_latitude: 55.8 },
    grid_cell_m: 250,
    grid_cols: 42,
    grid_rows: 45,
    total_cells: 1890,
    covered_cells: 1,
    coverage_ratio: 0.0005,
    gap_cells: 1889,
    covered_cell_counts: [{ cx: 10, cy: 20, observations: 7 }],
    routes: [],
    note: 'test',
  };

  it('формула ячеек повторяет backend (equirectangular, mid_lat)', () => {
    const g = coverageGrid(coverage as never);
    expect(g.cellLat).toBeCloseTo(250 / 111320, 10);
    const midLat = (55.7 + 55.8) / 2;
    expect(g.cellLon).toBeCloseTo(250 / (111320 * Math.cos((midLat * Math.PI) / 180)), 10);
  });

  it('ячейка (cx,cy) строится от min_lon/min_lat', () => {
    const fc = coverageCells(coverage as never);
    expect(fc.features).toHaveLength(1);
    const g = coverageGrid(coverage as never);
    const ring = (fc.features[0].geometry as GeoJSON.Polygon).coordinates[0];
    expect(ring[0][0]).toBeCloseTo(37.55 + 10 * g.cellLon, 10);
    expect(ring[0][1]).toBeCloseTo(55.7 + 20 * g.cellLat, 10);
    expect(fc.features[0].properties?.observations).toBe(7);
  });

  it('пустое покрытие даёт пустой слой', () => {
    expect(coverageCells(null).features).toHaveLength(0);
  });
});

describe('состояние карты: URL-сериализация', () => {
  it('дефолты: 2D, network, наблюдения выключены', () => {
    const s = parseMapState(new URLSearchParams());
    expect(s.mode).toBe('2d');
    expect(s.view).toBe('network');
    expect(s.layers.observations).toBe(false);
    expect(s.layers.assets).toBe(true);
    expect(s.selection).toBeNull();
    expect(s.camera).toBeNull();
  });

  it('infrastructure view включает наблюдения и покрытие по умолчанию', () => {
    const s = parseMapState(new URLSearchParams('view=infrastructure'));
    expect(s.layers.observations).toBe(true);
    expect(s.layers.coverage).toBe(true);
  });

  it('roundtrip: mode/camera/layers/filters/selection/time', () => {
    const s = parseMapState(new URLSearchParams());
    s.mode = '3d';
    s.camera = { center: [37.6173, 55.7558], zoom: 15.5, pitch: 55, bearing: -15 };
    s.layers = { ...defaultLayers('network'), observations: true, hexbin: true };
    s.filters = { asset_type: 'pole', priority_band: 'HIGH_PRIORITY', defect_status: 'OPEN', severity_min: '4' };
    s.selection = { layer: 'assets', id: 'asset-1' };
    s.timeRange = { from: '2026-11-01', to: '2026-11-10' };
    const params = serializeMapState(new URLSearchParams(), s);
    const back = parseMapState(params);
    expect(back.mode).toBe('3d');
    expect(back.camera?.center).toEqual([37.6173, 55.7558]);
    expect(back.camera?.pitch).toBe(55);
    expect(back.layers.observations).toBe(true);
    expect(back.layers.hexbin).toBe(true);
    expect(back.layers.coverage).toBe(false);
    expect(back.filters).toEqual(s.filters);
    expect(back.selection).toEqual(s.selection);
    expect(back.timeRange).toEqual(s.timeRange);
  });

  it('переключение 2D→3D не сбрасывает selection и фильтры', () => {
    const params = serializeMapState(
      new URLSearchParams(),
      { ...parseMapState(new URLSearchParams('selected=a1&layer=assets&asset_type=pole')), mode: '2d' },
    );
    const next = new URLSearchParams(params);
    next.set('mode', '3d');
    const s = parseMapState(next);
    expect(s.mode).toBe('3d');
    expect(s.selection).toEqual({ layer: 'assets', id: 'a1' });
    expect(s.filters.asset_type).toBe('pole');
  });

  it('невалидная камера и неизвестный layer отклоняются', () => {
    expect(parseCamera('abc')).toBeNull();
    expect(parseCamera('12,37.6,55.7,0')).toBeNull();
    expect(parseCamera('12,37.6,999,0,0')).toBeNull();
    const cam = parseCamera('15.50,37.61730,55.75580,55.0,-15.0');
    expect(cam?.zoom).toBe(15.5);
    expect(serializeCamera(cam!)).toBe('15.50,37.61730,55.75580,55.0,-15.0');
    const s = parseMapState(new URLSearchParams('selected=x&layer=unknown'));
    expect(s.selection).toBeNull();
  });

  it('лишние параметры URL сохраняются при сериализации', () => {
    const s = parseMapState(new URLSearchParams('stats=1'));
    const params = serializeMapState(new URLSearchParams('stats=1'), s);
    expect(params.get('stats')).toBe('1');
  });
});
