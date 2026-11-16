import { useEffect, useRef } from 'react';
import maplibregl, { type Map as MLMap, type MapMouseEvent, type Popup } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import type {
  AssetMapCollection,
  DefectMapCollection,
  ObservationMapCollection,
  RouteMapCollection,
} from '../../api/types';

export interface MapSelection {
  layer: 'assets' | 'defects' | 'observations' | 'routes';
  id: string;
  properties: Record<string, unknown>;
  lon: number;
  lat: number;
}

export interface LayerVisibility {
  assets: boolean;
  defects: boolean;
  observations: boolean;
  routes: boolean;
}

export const BAND_COLORS: Record<string, string> = {
  HIGH_PRIORITY: '#E66C61',
  MEDIUM_PRIORITY: '#F0A45C',
  LOW_PRIORITY: '#9DBFA8',
  NEEDS_REVIEW: '#75D7CC',
};

const BASEMAP_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    esriBase: {
      type: 'raster',
      tiles: [
        'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}',
      ],
      tileSize: 256,
      maxzoom: 16,
      attribution: '© Esri · HERE · Garmin · FAO · NOAA · USGS',
    },
    esriLabels: {
      type: 'raster',
      tiles: [
        'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}',
      ],
      tileSize: 256,
      maxzoom: 16,
    },
  },
  layers: [
    { id: 'esri-base', type: 'raster', source: 'esriBase' },
    { id: 'esri-labels', type: 'raster', source: 'esriLabels' },
  ],
};

const EMPTY: maplibregl.GeoJSONSourceSpecification['data'] = { type: 'FeatureCollection', features: [] };

interface Props {
  assets?: AssetMapCollection | null;
  defects?: DefectMapCollection | null;
  observations?: ObservationMapCollection | null;
  routes?: RouteMapCollection | null;
  visible: LayerVisibility;
  selectedId?: string | null;
  onSelect?: (sel: MapSelection | null) => void;
  onFallback?: () => void;
  className?: string;
}

export default function MapView({ assets, defects, observations, routes, visible, selectedId, onSelect, onFallback, className }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const loadedRef = useRef(false);
  const popupRef = useRef<Popup | null>(null);
  const tileErrors = useRef(0);
  const propsRef = useRef({ onSelect, onFallback });
  propsRef.current = { onSelect, onFallback };

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    let map: MLMap;
    try {
      map = new maplibregl.Map({
        container: el,
        style: BASEMAP_STYLE,
        center: [37.6173, 55.7558],
        zoom: 12,
        attributionControl: { compact: true },
        dragRotate: false,
        pitchWithRotate: false,
      });
    } catch {
      propsRef.current.onFallback?.();
      return;
    }
    mapRef.current = map;
    map.touchZoomRotate.disableRotation();
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    map.on('error', (e) => {
      const msg = String((e as { error?: Error }).error?.message ?? '');
      if (/tile|fetch|network|Failed/i.test(msg)) {
        tileErrors.current += 1;
        if (tileErrors.current > 8) propsRef.current.onFallback?.();
      }
    });
    map.on('webglcontextlost', () => propsRef.current.onFallback?.());

    map.on('load', () => {
      loadedRef.current = true;
      map.addSource('routes', { type: 'geojson', data: EMPTY });
      map.addSource('observations', { type: 'geojson', data: EMPTY });
      map.addSource('assets', { type: 'geojson', data: EMPTY, cluster: true, clusterMaxZoom: 13, clusterRadius: 42 });
      map.addSource('defects', { type: 'geojson', data: EMPTY });
      map.addSource('selection', { type: 'geojson', data: EMPTY });

      map.addLayer({
        id: 'routes-line',
        type: 'line',
        source: 'routes',
        paint: { 'line-color': '#3D8A81', 'line-width': 2.4, 'line-opacity': 0.85 },
        layout: { 'line-cap': 'round', 'line-join': 'round' },
      });
      map.addLayer({
        id: 'obs-points',
        type: 'circle',
        source: 'observations',
        paint: {
          'circle-radius': 4,
          'circle-color': ['match', ['get', 'review_status'], 'UNREVIEWED', '#F0A45C', '#75D7CC'],
          'circle-opacity': 0.75,
          'circle-stroke-width': 1,
          'circle-stroke-color': '#091318',
        },
      });
      map.addLayer({
        id: 'asset-clusters',
        type: 'circle',
        source: 'assets',
        filter: ['has', 'point_count'],
        paint: {
          'circle-color': '#1C3038',
          'circle-radius': ['step', ['get', 'point_count'], 14, 5, 18, 12, 23],
          'circle-stroke-width': 1.5,
          'circle-stroke-color': '#75D7CC',
        },
      });
      map.addLayer({
        id: 'asset-cluster-count',
        type: 'symbol',
        source: 'assets',
        filter: ['has', 'point_count'],
        layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-size': 12, 'text-font': ['Open Sans Semibold'] },
        paint: { 'text-color': '#E9EEE9' },
      });
      map.addLayer({
        id: 'asset-points',
        type: 'circle',
        source: 'assets',
        filter: ['!', ['has', 'point_count']],
        paint: {
          'circle-radius': 7,
          'circle-color': [
            'match',
            ['get', 'priority_band'],
            'HIGH_PRIORITY', BAND_COLORS.HIGH_PRIORITY,
            'MEDIUM_PRIORITY', BAND_COLORS.MEDIUM_PRIORITY,
            'LOW_PRIORITY', BAND_COLORS.LOW_PRIORITY,
            BAND_COLORS.NEEDS_REVIEW,
          ],
          'circle-stroke-width': 2,
          'circle-stroke-color': '#091318',
        },
      });
      map.addLayer({
        id: 'defect-rings',
        type: 'circle',
        source: 'defects',
        paint: {
          'circle-radius': 12,
          'circle-color': 'rgba(0,0,0,0)',
          'circle-stroke-width': 2,
          'circle-stroke-color': ['case', ['>=', ['get', 'severity'], 4], '#E66C61', '#F0A45C'],
          'circle-stroke-opacity': 0.9,
        },
      });
      map.addLayer({
        id: 'selection-ring',
        type: 'circle',
        source: 'selection',
        paint: {
          'circle-radius': 15,
          'circle-color': 'rgba(117,215,204,0.14)',
          'circle-stroke-width': 2,
          'circle-stroke-color': '#E9EEE9',
        },
      });

      const interactive = ['asset-points', 'asset-clusters', 'defect-rings', 'obs-points', 'routes-line'];
      interactive.forEach((layerId) => {
        map.on('mouseenter', layerId, () => {
          map.getCanvas().style.cursor = 'pointer';
        });
        map.on('mouseleave', layerId, () => {
          map.getCanvas().style.cursor = '';
          popupRef.current?.remove();
        });
      });

      const popup = new maplibregl.Popup({ closeButton: false, closeOnClick: false, offset: 12, className: 'revizor-map-popup' });
      popupRef.current = popup;
      map.on('mousemove', 'asset-points', (e: maplibregl.MapLayerMouseEvent) => {
        const f = e.features?.[0];
        if (!f) return;
        const name = String(f.properties?.display_name ?? f.properties?.external_id ?? 'Объект');
        popup.setLngLat(e.lngLat).setHTML(`<span>${escapeHtml(name)}</span>`).addTo(map);
      });

      map.on('click', (e: MapMouseEvent) => {
        const features = map.queryRenderedFeatures(e.point, { layers: interactive.filter((l) => map.getLayer(l)) });
        const f = features[0];
        if (!f) {
          propsRef.current.onSelect?.(null);
          return;
        }
        const layerId = f.layer?.id ?? '';
        if (layerId === 'asset-clusters') {
          const clusterId = f.properties?.cluster_id as number;
          const src = map.getSource('assets') as maplibregl.GeoJSONSource;
          src.getClusterExpansionZoom(clusterId).then((zoom) => {
            const g = f.geometry as GeoJSON.Point;
            map.easeTo({ center: g.coordinates as [number, number], zoom });
          }).catch(() => undefined);
          return;
        }
        const coords =
          f.geometry.type === 'Point'
            ? (f.geometry.coordinates as [number, number])
            : (e.lngLat.toArray() as [number, number]);
        const layer: MapSelection['layer'] =
          layerId === 'asset-points' ? 'assets'
          : layerId === 'defect-rings' ? 'defects'
          : layerId === 'obs-points' ? 'observations'
          : 'routes';
        propsRef.current.onSelect?.({
          layer,
          id: String(f.properties?.id ?? ''),
          properties: (f.properties ?? {}) as Record<string, unknown>,
          lon: coords[0],
          lat: coords[1],
        });
      });

      syncData(map, { assets, defects, observations, routes, visible, selectedId });
      fitToData(map, { assets, defects, observations, routes, visible });
    });

    const ro = new ResizeObserver(() => map.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
      popupRef.current?.remove();
      loadedRef.current = false;
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current) return;
    syncData(map, { assets, defects, observations, routes, visible, selectedId });
  }, [assets, defects, observations, routes, visible, selectedId]);

  const fitKey = `${assets?.features.length ?? 0}:${defects?.features.length ?? 0}:${routes?.features.length ?? 0}`;
  const firstFit = useRef(true);
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !loadedRef.current || !firstFit.current) return;
    if ((assets?.features.length ?? 0) + (routes?.features.length ?? 0) > 0) {
      fitToData(map, { assets, defects, observations, routes, visible });
      firstFit.current = false;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey]);

  return <div ref={containerRef} className={className} style={{ width: '100%', height: '100%', minHeight: 280 }} aria-label="Карта инфраструктуры" role="application" />;
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);
}

function syncData(
  map: MLMap,
  d: {
    assets?: AssetMapCollection | null;
    defects?: DefectMapCollection | null;
    observations?: ObservationMapCollection | null;
    routes?: RouteMapCollection | null;
    visible: LayerVisibility;
    selectedId?: string | null;
  },
) {
  const set = (id: string, data: unknown) => {
    const src = map.getSource(id) as maplibregl.GeoJSONSource | undefined;
    src?.setData((data ?? EMPTY) as maplibregl.GeoJSONSourceSpecification['data']);
  };
  set('assets', d.assets);
  set('defects', d.defects);
  set('observations', d.observations);
  set('routes', d.routes);

  const vis: [string, boolean][] = [
    ['routes-line', d.visible.routes],
    ['obs-points', d.visible.observations],
    ['asset-clusters', d.visible.assets],
    ['asset-cluster-count', d.visible.assets],
    ['asset-points', d.visible.assets],
    ['defect-rings', d.visible.defects],
  ];
  vis.forEach(([layer, on]) => {
    if (map.getLayer(layer)) map.setLayoutProperty(layer, 'visibility', on ? 'visible' : 'none');
  });

  let sel: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] };
  if (d.selectedId) {
    const all = [
      ...(d.assets?.features ?? []),
      ...(d.defects?.features ?? []),
      ...(d.observations?.features ?? []),
    ];
    const f = all.find((x) => x.properties?.id === d.selectedId && x.geometry?.type === 'Point');
    if (f?.geometry) {
      sel = {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            geometry: { type: 'Point', coordinates: f.geometry.coordinates as number[] },
            properties: {},
          },
        ],
      };
    }
  }
  set('selection', sel);
}

type CoordFeature = {
  geometry: { type: 'Point'; coordinates: number[] } | { type: 'LineString'; coordinates: number[][] } | null;
};

function eachCoord(fc: { features: CoordFeature[] } | null | undefined, cb: (lon: number, lat: number) => void): void {
  fc?.features.forEach((f) => {
    const g = f.geometry;
    if (!g) return;
    if (g.type === 'Point') cb(g.coordinates[0], g.coordinates[1]);
    else g.coordinates.forEach((c) => cb(c[0], c[1]));
  });
}

function fitToData(
  map: MLMap,
  d: {
    assets?: AssetMapCollection | null;
    defects?: DefectMapCollection | null;
    observations?: ObservationMapCollection | null;
    routes?: RouteMapCollection | null;
    visible: LayerVisibility;
  },
) {
  const coords: [number, number][] = [];
  const push = (lon: number, lat: number) => coords.push([lon, lat]);
  if (d.visible.assets) eachCoord(d.assets, push);
  if (d.visible.defects) eachCoord(d.defects, push);
  if (d.visible.routes) eachCoord(d.routes, push);
  if (coords.length === 0) return;
  const lons = coords.map((c) => c[0]);
  const lats = coords.map((c) => c[1]);
  map.fitBounds(
    [
      [Math.min(...lons), Math.min(...lats)],
      [Math.max(...lons), Math.max(...lats)],
    ],
    { padding: 64, maxZoom: 15, duration: 600 },
  );
}