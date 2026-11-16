/* Генерация self-hosted vector style для карты Revizor из OpenFreeMap fiord.
   Запуск: node scripts/build-map-style.mjs  (требует сеть; результат коммитится).
   Палитра приведена к токенам дизайн-системы (graphite/teal), добавлен fill-extrusion
   слой зданий с реальными высотами OpenMapTiles (render_height/render_min_height). */

const SOURCE_URL = 'https://tiles.openfreemap.org/styles/fiord';
const OUT = new URL('../public/styles/revizor-dark.json', import.meta.url);

const res = await fetch(SOURCE_URL);
if (!res.ok) throw new Error(`style fetch failed: ${res.status}`);
const style = await res.json();

const C = {
  bg: '#091318',
  surface: '#102129',
  raised: '#1c3038',
  line: '#24404a',
  lineSoft: '#1a313a',
  water: '#0c1a21',
  waterLine: '#14262e',
  green: '#12261f',
  greenLine: '#1d3a30',
  wood: '#10241f',
  building: '#16262e',
  roadMinor: '#1c3038',
  roadMajor: '#24404a',
  roadMotorway: '#2c4a56',
  casing: '#0c1a21',
  ink: '#e9eee9',
  muted: '#a0b3b5',
  faint: '#7d959b',
  control: '#55707a',
};

const fillByLayer = {
  background: C.bg,
  water: C.water,
  landcover_ice_shelf: C.surface,
  landuse_residential: '#0e1c23',
  landcover_wood: C.wood,
  park: C.green,
  building: C.building,
  'aeroway-area': C.surface,
  road_area_pier: C.surface,
};

const lineByLayer = {
  waterway: C.waterLine,
  park_outline: C.greenLine,
  'aeroway-taxiway': C.lineSoft,
  'aeroway-runway-casing': C.casing,
  'aeroway-runway': C.lineSoft,
  road_pier: C.lineSoft,
  highway_path: C.lineSoft,
  highway_minor: C.roadMinor,
  highway_major_casing: C.casing,
  highway_major_inner: C.roadMajor,
  highway_major_subtle: C.lineSoft,
  highway_motorway_casing: C.casing,
  highway_motorway_inner: C.roadMotorway,
  highway_motorway_subtle: C.line,
  tunnel_motorway_casing: C.casing,
  tunnel_motorway_inner: C.lineSoft,
  railway_transit: C.lineSoft,
  railway_transit_dashline: C.line,
  railway_service: C.lineSoft,
  railway_service_dashline: C.line,
  railway: C.lineSoft,
  railway_dashline: C.line,
  boundary_state: C.line,
  'boundary_country_z0-4': C.control,
  'boundary_country_z5-': C.control,
};

for (const layer of style.layers) {
  const paint = layer.paint ?? {};
  if (layer.type === 'background') {
    layer.paint = { 'background-color': C.bg };
    continue;
  }
  if (layer.type === 'fill' && fillByLayer[layer.id]) {
    paint['fill-color'] = fillByLayer[layer.id];
    if (layer.id === 'building') paint['fill-opacity'] = 0.9;
    if (layer.id === 'water') paint['fill-opacity'] = 1;
  }
  if (layer.type === 'line' && lineByLayer[layer.id]) {
    paint['line-color'] = lineByLayer[layer.id];
  }
  if (layer.type === 'symbol') {
    const isPlace = layer.id.startsWith('place_');
    const isWater = layer.id === 'water_name';
    const isRoad = layer.id.startsWith('highway_name') || layer.id === 'highway_ref';
    paint['text-color'] = isWater ? C.control : isRoad ? C.faint : isPlace ? C.muted : C.muted;
    if (layer.id === 'place_city' || layer.id === 'place_city_large' || layer.id === 'place_country_major') {
      paint['text-color'] = C.ink;
    }
    paint['text-halo-color'] = C.bg;
    paint['text-halo-width'] = layer.id === 'highway_ref' ? 1.5 : 1.2;
  }
  layer.paint = paint;
}

const firstSymbol = style.layers.find((l) => l.type === 'symbol');
const buildings3d = {
  id: 'building-3d',
  type: 'fill-extrusion',
  source: 'openmaptiles',
  'source-layer': 'building',
  minzoom: 13,
  layout: { visibility: 'none' },
  paint: {
    'fill-extrusion-color': [
      'interpolate', ['linear'], ['get', 'render_height'],
      0, '#14242c',
      30, '#1c3038',
      100, '#2a4550',
    ],
    'fill-extrusion-height': [
      'interpolate', ['linear'], ['zoom'],
      13, 0,
      13.5, ['get', 'render_height'],
    ],
    'fill-extrusion-base': [
      'interpolate', ['linear'], ['zoom'],
      13, 0,
      13.5, ['get', 'render_min_height'],
    ],
    'fill-extrusion-opacity': 0.92,
    'fill-extrusion-vertical-gradient': true,
  },
};
const idx = style.layers.indexOf(firstSymbol);
style.layers.splice(idx, 0, buildings3d);

style.metadata = {
  'revizor:generator': 'scripts/build-map-style.mjs',
  'revizor:source': SOURCE_URL,
  'revizor:note': 'Graphite restyle of OpenFreeMap fiord; building heights are OSM render_height/render_min_height (may be level-based estimates).',
};

const { mkdir, writeFile } = await import('node:fs/promises');
await mkdir(new URL('.', OUT), { recursive: true });
await writeFile(OUT, JSON.stringify(style, null, 1) + '\n');
console.log(`written ${OUT.pathname} (${style.layers.length} layers)`);
