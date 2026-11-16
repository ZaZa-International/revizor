/* Единое состояние карты: URL — единственный источник истины.
   Синхронизирует карту, панели, фильтры и реестр; переживает reload и deep-link.
   Переключение 2D/3D меняет только mode/camera — selection и фильтры сохраняются. */

import { useCallback, useMemo, useRef } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { GeoKind, MapCamera, MapMode } from './types';

export type MapViewKind = 'network' | 'infrastructure';

export interface MapLayers {
  assets: boolean;
  defects: boolean;
  observations: boolean;
  routes: boolean;
  coverage: boolean;
  heatmap: boolean;
  hexbin: boolean;
}

export interface MapFilters {
  asset_type: string;
  priority_band: string;
  defect_status: string;
  severity_min: string;
}

export interface MapSelectionRef {
  layer: GeoKind;
  id: string;
}

export interface MapState {
  mode: MapMode;
  view: MapViewKind;
  camera: MapCamera | null;
  layers: MapLayers;
  filters: MapFilters;
  selection: MapSelectionRef | null;
  timeRange: { from: string; to: string };
}

const CORE_LAYERS = ['assets', 'defects', 'observations', 'routes'] as const;
const EXTRA_LAYERS = ['coverage', 'heatmap', 'hexbin'] as const;
const ALL_LAYERS = [...CORE_LAYERS, ...EXTRA_LAYERS];
const GEO_KINDS: GeoKind[] = ['assets', 'defects', 'observations', 'routes'];

export function defaultLayers(view: MapViewKind): MapLayers {
  return {
    assets: true,
    defects: true,
    observations: view === 'infrastructure',
    routes: true,
    coverage: view === 'infrastructure',
    heatmap: false,
    hexbin: false,
  };
}

export function defaultState(view: MapViewKind = 'network'): MapState {
  return {
    mode: '2d',
    view,
    camera: null,
    layers: defaultLayers(view),
    filters: { asset_type: '', priority_band: '', defect_status: '', severity_min: '' },
    selection: null,
    timeRange: { from: '', to: '' },
  };
}

function clamp(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, v));
}

export function parseCamera(raw: string | null): MapCamera | null {
  if (!raw) return null;
  const parts = raw.split(',').map(Number);
  if (parts.length !== 5 || parts.some((n) => !Number.isFinite(n))) return null;
  const [zoom, lon, lat, pitch, bearing] = parts;
  if (lon < -180 || lon > 180 || lat < -90 || lat > 90) return null;
  return {
    center: [lon, lat],
    zoom: clamp(zoom, 0, 22),
    pitch: clamp(pitch, 0, 60),
    bearing: clamp(bearing, -180, 180),
  };
}

export function serializeCamera(c: MapCamera): string {
  return [
    c.zoom.toFixed(2),
    c.center[0].toFixed(5),
    c.center[1].toFixed(5),
    c.pitch.toFixed(1),
    c.bearing.toFixed(1),
  ].join(',');
}

export function parseMapState(params: URLSearchParams): MapState {
  const view: MapViewKind = params.get('view') === 'infrastructure' ? 'infrastructure' : 'network';
  const base = defaultState(view);
  const mode: MapMode = params.get('mode') === '3d' ? '3d' : '2d';

  const layersRaw = params.get('layers');
  let layers = base.layers;
  if (layersRaw !== null) {
    const enabled = new Set(layersRaw.split(',').filter((l) => (ALL_LAYERS as string[]).includes(l)));
    layers = Object.fromEntries(ALL_LAYERS.map((l) => [l, enabled.has(l)])) as unknown as MapLayers;
  }

  const selected = params.get('selected');
  const layerRaw = params.get('layer') as GeoKind | null;
  const selection: MapSelectionRef | null =
    selected && layerRaw && GEO_KINDS.includes(layerRaw) ? { layer: layerRaw, id: selected } : null;

  return {
    mode,
    view,
    camera: parseCamera(params.get('cam')),
    layers,
    filters: {
      asset_type: params.get('asset_type') ?? '',
      priority_band: params.get('priority_band') ?? '',
      defect_status: params.get('defect_status') ?? '',
      severity_min: params.get('severity_min') ?? '',
    },
    selection,
    timeRange: { from: params.get('from') ?? '', to: params.get('to') ?? '' },
  };
}

export function serializeMapState(params: URLSearchParams, state: MapState): URLSearchParams {
  const next = new URLSearchParams(params);
  const base = defaultState(state.view);

  const setOrDelete = (key: string, value: string, defaultValue: string) => {
    if (value && value !== defaultValue) next.set(key, value);
    else next.delete(key);
  };

  setOrDelete('mode', state.mode, '2d');
  setOrDelete('view', state.view, 'network');
  if (state.camera) next.set('cam', serializeCamera(state.camera));
  else next.delete('cam');

  const enabled = ALL_LAYERS.filter((l) => state.layers[l]);
  const defaultEnabled = ALL_LAYERS.filter((l) => base.layers[l]);
  if (enabled.join(',') !== defaultEnabled.join(',')) next.set('layers', enabled.join(','));
  else next.delete('layers');

  setOrDelete('asset_type', state.filters.asset_type, '');
  setOrDelete('priority_band', state.filters.priority_band, '');
  setOrDelete('defect_status', state.filters.defect_status, '');
  setOrDelete('severity_min', state.filters.severity_min, '');
  setOrDelete('from', state.timeRange.from, '');
  setOrDelete('to', state.timeRange.to, '');

  if (state.selection) {
    next.set('selected', state.selection.id);
    next.set('layer', state.selection.layer);
  } else {
    next.delete('selected');
    next.delete('layer');
  }
  return next;
}

export interface MapStateApi {
  state: MapState;
  update: (patch: Partial<MapState>) => void;
  select: (selection: MapSelectionRef | null) => void;
  setMode: (mode: MapMode) => void;
  setView: (view: MapViewKind) => void;
  setCamera: (camera: MapCamera | null) => void;
  toggleLayer: (layer: keyof MapLayers) => void;
  setFilter: (key: keyof MapFilters, value: string) => void;
  setTimeRange: (from: string, to: string) => void;
}

export function useMapState(): MapStateApi {
  const [params, setParams] = useSearchParams();
  const paramsRef = useRef(params);
  paramsRef.current = params;
  const state = useMemo(() => parseMapState(params), [params]);

  const update = useCallback(
    (patch: Partial<MapState>) => {
      const prev = paramsRef.current;
      const current = parseMapState(prev);
      const merged: MapState = {
        ...current,
        ...patch,
        layers: patch.layers ?? current.layers,
        filters: patch.filters ?? current.filters,
        timeRange: patch.timeRange ?? current.timeRange,
      };
      if (patch.view && patch.view !== current.view && !patch.layers) {
        merged.layers = defaultLayers(patch.view);
      }
      const next = serializeMapState(prev, merged);
      paramsRef.current = next;
      setParams(next, { replace: true });
    },
    [setParams],
  );

  const select = useCallback((selection: MapSelectionRef | null) => update({ selection }), [update]);
  const setMode = useCallback((mode: MapMode) => update({ mode }), [update]);
  const setView = useCallback((view: MapViewKind) => update({ view }), [update]);
  const setCamera = useCallback((camera: MapCamera | null) => update({ camera }), [update]);
  const toggleLayer = useCallback(
    (layer: keyof MapLayers) => {
      update({ layers: { ...state.layers, [layer]: !state.layers[layer] } });
    },
    [update, state.layers],
  );
  const setFilter = useCallback(
    (key: keyof MapFilters, value: string) => update({ filters: { ...state.filters, [key]: value } }),
    [update, state.filters],
  );
  const setTimeRange = useCallback(
    (from: string, to: string) => update({ timeRange: { from, to } }),
    [update],
  );

  return { state, update, select, setMode, setView, setCamera, toggleLayer, setFilter, setTimeRange };
}
