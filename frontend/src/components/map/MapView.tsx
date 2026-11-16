import { useEffect, useMemo, useRef } from 'react';
import maplibregl, { type Map as MLMap, type MapMouseEvent, type Popup } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import type {
  AssetMapCollection,
  DefectMapCollection,
  ObservationMapCollection,
  RouteMapCollection,
} from '../../api/types';
import {
  accuracyCollection,
  adaptCollection,
  boundsOf,
  emptyCollection,
  findFeature,
  selectionCollection,
} from '../../geo/adapter';
import { GEO_COLORS } from '../../geo/palette';
import { serializeCamera } from '../../geo/state';
import type { MapCamera, MapMode } from '../../geo/types';

export { BAND_COLORS } from '../../geo/palette';

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

export interface MapStats {
  features: number;
  layers: number;
  rejected: number;
}

const VECTOR_STYLE_URL = '/styles/revizor-dark.json';

const ESRI_FALLBACK_STYLE: maplibregl.StyleSpecification = {
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

const EMPTY = emptyCollection();

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
  mode?: MapMode;
  camera?: MapCamera | null;
  onCameraChange?: (camera: MapCamera) => void;
  onViewportChange?: (bbox: string) => void;
  coverage?: GeoJSON.FeatureCollection | null;
  coverageOutline?: GeoJSON.FeatureCollection | null;
  showCoverage?: boolean;
  showHeatmap?: boolean;
  showAccuracy?: boolean;
  fitSignal?: number;
  onMapReady?: (map: MLMap | null) => void;
  onStats?: (stats: MapStats) => void;
}

export default function MapView({
  assets,
  defects,
  observations,
  routes,
  visible,
  selectedId,
  onSelect,
  onFallback,
  className,
  mode = '2d',
  camera = null,
  onCameraChange,
  onViewportChange,
  coverage = null,
  coverageOutline = null,
  showCoverage = false,
  showHeatmap = false,
  showAccuracy = false,
  fitSignal = 0,
  onMapReady,
  onStats,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MLMap | null>(null);
  const installedRef = useRef(false);
  const popupRef = useRef<Popup | null>(null);
  const tileErrors = useRef(0);
  const rasterTried = useRef(false);
  const lastEmittedCamera = useRef<string | null>(null);
  const prevSelectedRef = useRef<string | null>(null);
  const firstFit = useRef(true);
  const restoredCamera = useRef(camera != null);
  const expectMove = useRef(false);

  const adapted = useMemo(
    () => ({
      assets: adaptCollection('assets', assets),
      defects: adaptCollection('defects', defects),
      observations: adaptCollection('observations', observations),
      routes: adaptCollection('routes', routes),
    }),
    [assets, defects, observations, routes],
  );

  const propsRef = useRef({ onSelect, onFallback, onCameraChange, onViewportChange, onMapReady, onStats });
  propsRef.current = { onSelect, onFallback, onCameraChange, onViewportChange, onMapReady, onStats };
  const dataRef = useRef({ adapted, visible, selectedId, coverage, coverageOutline, showCoverage, showHeatmap, showAccuracy, mode, camera });
  dataRef.current = { adapted, visible, selectedId, coverage, coverageOutline, showCoverage, showHeatmap, showAccuracy, mode, camera };

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    let map: MLMap;
    try {
      map = new maplibregl.Map({
        container: el,
        style: VECTOR_STYLE_URL,
        center: [37.6173, 55.7558],
        zoom: 12,
        maxPitch: 60,
        attributionControl: { compact: true },
        dragRotate: true,
        pitchWithRotate: true,
      });
    } catch {
      propsRef.current.onFallback?.();
      return;
    }
    mapRef.current = map;
    (el as HTMLDivElement & { __revizorMap?: MLMap }).__revizorMap = map;
    map.touchZoomRotate.disableRotation();
    map.addControl(new maplibregl.NavigationControl({ showCompass: true }), 'top-right');
    propsRef.current.onMapReady?.(map);

    const emitViewport = (e?: { originalEvent?: unknown }) => {
      if (!e?.originalEvent && !expectMove.current) return;
      expectMove.current = false;
      const b = map.getBounds();
      const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]
        .map((n) => n.toFixed(4))
        .join(',');
      propsRef.current.onViewportChange?.(bbox);
      const cam: MapCamera = {
        center: [map.getCenter().lng, map.getCenter().lat],
        zoom: map.getZoom(),
        pitch: map.getPitch(),
        bearing: map.getBearing(),
      };
      lastEmittedCamera.current = serializeCamera(cam);
      propsRef.current.onCameraChange?.(cam);
    };
    map.on('moveend', emitViewport);

    map.on('error', (e) => {
      const msg = String((e as { error?: Error }).error?.message ?? '');
      if (/tile|fetch|network|Failed|style/i.test(msg)) {
        tileErrors.current += 1;
        if (tileErrors.current > 8) {
          if (!rasterTried.current) {
            rasterTried.current = true;
            tileErrors.current = 0;
            installedRef.current = false;
            map.setStyle(ESRI_FALLBACK_STYLE);
            map.once('style.load', () => {
              installDataLayers(map);
              syncAll(map);
            });
          } else {
            propsRef.current.onFallback?.();
          }
        }
      }
    });
    map.on('webglcontextlost', () => propsRef.current.onFallback?.());

    map.on('load', () => {
      installDataLayers(map);
      syncAll(map);
      const d = dataRef.current;
      if (restoredCamera.current && d.camera) {
        applyCamera(map, d.camera);
        firstFit.current = false;
      } else {
        fitToData(map);
      }
      applyMode(map, d.mode, restoredCamera.current);
    });

    const ro = new ResizeObserver(() => map.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
      popupRef.current?.remove();
      installedRef.current = false;
      propsRef.current.onMapReady?.(null);
      delete (el as HTMLDivElement & { __revizorMap?: MLMap }).__revizorMap;
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !installedRef.current) return;
    syncAll(map);
  }, [adapted, visible, selectedId, coverage, coverageOutline, showCoverage, showHeatmap, showAccuracy]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !installedRef.current) return;
    applyMode(map, mode, camera != null);
  }, [mode, camera]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !installedRef.current || !camera) return;
    if (serializeCamera(camera) === lastEmittedCamera.current) return;
    applyCamera(map, camera);
    firstFit.current = false;
  }, [camera]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !installedRef.current || fitSignal === 0) return;
    fitToData(map);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitSignal]);

  const fitKey = `${adapted.assets.features.length}:${adapted.defects.features.length}:${adapted.routes.features.length}`;
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !installedRef.current || !firstFit.current || restoredCamera.current) return;
    if (adapted.assets.features.length + adapted.routes.features.length > 0) {
      fitToData(map);
      firstFit.current = false;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fitKey]);

  function syncAll(map: MLMap) {
    const d = dataRef.current;
    const set = (id: string, data: GeoJSON.FeatureCollection) => {
      const src = map.getSource(id) as maplibregl.GeoJSONSource | undefined;
      src?.setData(data);
    };
    set('assets', d.adapted.assets.render);
    set('defects', d.adapted.defects.render);
    set('observations', d.adapted.observations.render);
    set('routes', d.adapted.routes.render);
    set('coverage', d.showCoverage ? (d.coverage ?? EMPTY) : EMPTY);
    set('coverage-outline', d.showCoverage ? (d.coverageOutline ?? EMPTY) : EMPTY);
    set('accuracy', d.showAccuracy ? accuracyCollection([d.adapted.assets, d.adapted.observations]) : EMPTY);

    const selFeature = findFeature(
      [d.adapted.assets, d.adapted.defects, d.adapted.observations, d.adapted.routes],
      d.selectedId,
    );
    set('selection', selectionCollection(selFeature));

    if (prevSelectedRef.current && prevSelectedRef.current !== d.selectedId) {
      try {
        map.removeFeatureState({ source: 'assets', id: prevSelectedRef.current });
      } catch {
        /* feature мог отсутствовать (кластер/другой слой) */
      }
    }
    if (d.selectedId && selFeature?.kind === 'assets') {
      try {
        map.setFeatureState({ source: 'assets', id: d.selectedId }, { selected: true });
      } catch {
        /* ignore */
      }
    }
    prevSelectedRef.current = d.selectedId ?? null;

    const vis: [string, boolean][] = [
      ['coverage-cells', d.showCoverage],
      ['coverage-outline', d.showCoverage],
      ['routes-line', d.visible.routes],
      ['obs-heatmap', d.showHeatmap && d.visible.observations],
      ['obs-points', d.visible.observations],
      ['accuracy-fill', d.showAccuracy],
      ['accuracy-line', d.showAccuracy],
      ['asset-clusters', d.visible.assets],
      ['asset-cluster-count', d.visible.assets],
      ['asset-points', d.visible.assets],
      ['defect-rings', d.visible.defects],
    ];
    vis.forEach(([layer, on]) => {
      if (map.getLayer(layer)) map.setLayoutProperty(layer, 'visibility', on ? 'visible' : 'none');
    });
    if (map.getLayer('obs-points')) {
      map.setPaintProperty('obs-points', 'circle-opacity', d.showHeatmap ? 0.35 : 0.75);
    }

    const features =
      d.adapted.assets.features.length +
      d.adapted.defects.features.length +
      d.adapted.observations.features.length +
      d.adapted.routes.features.length;
    const rejected =
      d.adapted.assets.rejected.length +
      d.adapted.defects.rejected.length +
      d.adapted.observations.rejected.length +
      d.adapted.routes.rejected.length;
    propsRef.current.onStats?.({
      features,
      layers: map.getStyle().layers?.length ?? 0,
      rejected,
    });
  }

  function installDataLayers(map: MLMap) {
    if (installedRef.current) return;
    const style = map.getStyle();
    const beforeId = style?.layers?.find((l) => l.type === 'symbol')?.id;

    map.addSource('coverage', { type: 'geojson', data: EMPTY });
    map.addSource('coverage-outline', { type: 'geojson', data: EMPTY });
    map.addSource('routes', { type: 'geojson', data: EMPTY });
    map.addSource('observations', { type: 'geojson', data: EMPTY });
    map.addSource('assets', {
      type: 'geojson',
      data: EMPTY,
      cluster: true,
      clusterMaxZoom: 13,
      clusterRadius: 42,
      promoteId: 'id',
    });
    map.addSource('defects', { type: 'geojson', data: EMPTY });
    map.addSource('accuracy', { type: 'geojson', data: EMPTY });
    map.addSource('selection', { type: 'geojson', data: EMPTY });

    map.addLayer({
      id: 'coverage-cells',
      type: 'fill',
      source: 'coverage',
      layout: { visibility: 'none' },
      paint: {
        'fill-color': [
          'interpolate', ['linear'], ['get', 'observations'],
          0, GEO_COLORS.coverageLow,
          5, GEO_COLORS.accentDim,
          20, GEO_COLORS.coverageHigh,
        ],
        'fill-opacity': 0.22,
      },
    }, beforeId);
    map.addLayer({
      id: 'coverage-outline',
      type: 'line',
      source: 'coverage-outline',
      layout: { visibility: 'none' },
      paint: { 'line-color': GEO_COLORS.control, 'line-width': 1, 'line-dasharray': [2, 2] },
    }, beforeId);
    map.addLayer({
      id: 'routes-line',
      type: 'line',
      source: 'routes',
      paint: { 'line-color': ['get', '_color'], 'line-width': 2.4, 'line-opacity': 0.85 },
      layout: { 'line-cap': 'round', 'line-join': 'round' },
    }, beforeId);
    map.addLayer({
      id: 'obs-heatmap',
      type: 'heatmap',
      source: 'observations',
      layout: { visibility: 'none' },
      paint: {
        'heatmap-weight': 1,
        'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 10, 0.6, 15, 1.2],
        'heatmap-color': [
          'interpolate', ['linear'], ['heatmap-density'],
          0, 'rgba(9,19,24,0)',
          0.2, 'rgba(61,138,129,0.35)',
          0.5, 'rgba(117,215,204,0.55)',
          0.8, 'rgba(240,164,92,0.7)',
          1, 'rgba(230,108,97,0.85)',
        ],
        'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 10, 12, 15, 24],
        'heatmap-opacity': 0.8,
      },
    }, beforeId);
    map.addLayer({
      id: 'obs-points',
      type: 'circle',
      source: 'observations',
      paint: {
        'circle-radius': 4,
        'circle-color': ['get', '_color'],
        'circle-opacity': 0.75,
        'circle-stroke-width': 1,
        'circle-stroke-color': GEO_COLORS.bg,
      },
    }, beforeId);
    map.addLayer({
      id: 'accuracy-fill',
      type: 'fill',
      source: 'accuracy',
      layout: { visibility: 'none' },
      paint: { 'fill-color': GEO_COLORS.accent, 'fill-opacity': 0.07 },
    }, beforeId);
    map.addLayer({
      id: 'accuracy-line',
      type: 'line',
      source: 'accuracy',
      layout: { visibility: 'none' },
      paint: { 'line-color': GEO_COLORS.accent, 'line-width': 1, 'line-opacity': 0.4, 'line-dasharray': [1, 2] },
    }, beforeId);
    map.addLayer({
      id: 'asset-clusters',
      type: 'circle',
      source: 'assets',
      filter: ['has', 'point_count'],
      paint: {
        'circle-color': GEO_COLORS.raised,
        'circle-radius': ['step', ['get', 'point_count'], 14, 5, 18, 12, 23],
        'circle-stroke-width': 1.5,
        'circle-stroke-color': GEO_COLORS.accent,
      },
    }, beforeId);
    map.addLayer({
      id: 'asset-cluster-count',
      type: 'symbol',
      source: 'assets',
      filter: ['has', 'point_count'],
      layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-size': 12, 'text-font': ['Noto Sans Regular'] },
      paint: { 'text-color': GEO_COLORS.ink },
    }, beforeId);
    map.addLayer({
      id: 'asset-points',
      type: 'circle',
      source: 'assets',
      filter: ['!', ['has', 'point_count']],
      paint: {
        'circle-radius': ['case', ['boolean', ['feature-state', 'selected'], false], 10, 7],
        'circle-color': ['get', '_color'],
        'circle-stroke-width': ['case', ['boolean', ['feature-state', 'selected'], false], 3, 2],
        'circle-stroke-color': [
          'case',
          ['boolean', ['feature-state', 'selected'], false],
          GEO_COLORS.ink,
          GEO_COLORS.bg,
        ],
        'circle-radius-transition': { duration: 200 },
        'circle-stroke-width-transition': { duration: 200 },
      } as maplibregl.CircleLayerSpecification['paint'],
    }, beforeId);
    map.addLayer({
      id: 'defect-rings',
      type: 'circle',
      source: 'defects',
      paint: {
        'circle-radius': 12,
        'circle-color': 'rgba(0,0,0,0)',
        'circle-stroke-width': 2,
        'circle-stroke-color': ['get', '_ring'],
        'circle-stroke-opacity': 0.9,
      },
    }, beforeId);
    map.addLayer({
      id: 'selection-ring',
      type: 'circle',
      source: 'selection',
      paint: {
        'circle-radius': 15,
        'circle-color': 'rgba(117,215,204,0.14)',
        'circle-stroke-width': 2,
        'circle-stroke-color': GEO_COLORS.ink,
      },
    }, beforeId);

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
      const name = String(f.properties?._label ?? f.properties?.display_name ?? 'Объект');
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
            expectMove.current = true;
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

    installedRef.current = true;
  }

  function applyCamera(map: MLMap, cam: MapCamera) {
    expectMove.current = true;
    lastEmittedCamera.current = serializeCamera(cam);
    map.easeTo({ center: cam.center, zoom: cam.zoom, pitch: cam.pitch, bearing: cam.bearing, duration: 400 });
  }

  function applyMode(map: MLMap, m: MapMode, controlledCamera: boolean) {
    const has3d = !!map.getLayer('building-3d');
    if (has3d) {
      map.setLayoutProperty('building-3d', 'visibility', m === '3d' ? 'visible' : 'none');
      if (map.getLayer('building')) {
        map.setLayoutProperty('building', 'visibility', m === '3d' ? 'none' : 'visible');
      }
    }
    if (m === '3d') {
      map.dragRotate.enable();
      map.touchZoomRotate.enableRotation();
      if (!controlledCamera && map.getPitch() < 10) {
        expectMove.current = true;
        map.easeTo({ pitch: 55, duration: 500 });
      }
    } else {
      map.dragRotate.disable();
      map.touchZoomRotate.disableRotation();
      if (!controlledCamera && (map.getPitch() > 0 || map.getBearing() !== 0)) {
        expectMove.current = true;
        map.easeTo({ pitch: 0, bearing: 0, duration: 500 });
      }
    }
  }

  function fitToData(map: MLMap) {
    const d = dataRef.current;
    const layers = [];
    if (d.visible.assets) layers.push(d.adapted.assets);
    if (d.visible.defects) layers.push(d.adapted.defects);
    if (d.visible.routes) layers.push(d.adapted.routes);
    const bounds = boundsOf(layers);
    if (!bounds) return;
    expectMove.current = true;
    map.fitBounds(bounds, { padding: 64, maxZoom: 15, duration: 600 });
  }

  return <div ref={containerRef} className={className} style={{ width: '100%', height: '100%', minHeight: 280 }} aria-label="Карта инфраструктуры" role="application" />;
}

function escapeHtml(s: string): string {
  return s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);
}
