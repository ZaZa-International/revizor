import { lazy, Suspense, useCallback, useState } from 'react';
import SchematicMap from './SchematicMap';
import type { LayerVisibility, MapSelection, MapStats } from './MapView';
import type { MapCamera, MapMode } from '../../geo/types';
import type {
  AssetMapCollection,
  DefectMapCollection,
  ObservationMapCollection,
  RouteMapCollection,
} from '../../api/types';
import { LoadingState } from '../ui';

const MapView = lazy(() => import('./MapView'));

export type { LayerVisibility, MapSelection, MapStats };

interface Props {
  assets?: AssetMapCollection | null;
  defects?: DefectMapCollection | null;
  observations?: ObservationMapCollection | null;
  routes?: RouteMapCollection | null;
  visible: LayerVisibility;
  selectedId?: string | null;
  onSelect?: (sel: MapSelection | null) => void;
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
  onMapReady?: (map: import('maplibre-gl').Map | null) => void;
  onStats?: (stats: MapStats) => void;
}

function webglAvailable(): boolean {
  try {
    const canvas = document.createElement('canvas');
    return !!(canvas.getContext('webgl2') || canvas.getContext('webgl'));
  } catch {
    return false;
  }
}

export default function NetworkMap(props: Props) {
  const [fallback, setFallback] = useState(() => !webglAvailable());
  const onFallback = useCallback(() => setFallback(true), []);

  if (fallback) {
    return (
      <SchematicMap
        assets={props.assets}
        defects={props.defects}
        observations={props.observations}
        routes={props.routes}
        visible={props.visible}
        selectedId={props.selectedId}
        onSelect={props.onSelect}
        className={props.className}
      />
    );
  }
  return (
    <Suspense fallback={<LoadingState label="Загрузка карты…" />}>
      <MapView {...props} onFallback={onFallback} />
    </Suspense>
  );
}
