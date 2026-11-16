import { lazy, Suspense, useCallback, useState } from 'react';
import SchematicMap from './SchematicMap';
import type { LayerVisibility, MapSelection } from './MapView';
import type {
  AssetMapCollection,
  DefectMapCollection,
  ObservationMapCollection,
  RouteMapCollection,
} from '../../api/types';
import { LoadingState } from '../ui';

const MapView = lazy(() => import('./MapView'));

export type { LayerVisibility, MapSelection };

interface Props {
  assets?: AssetMapCollection | null;
  defects?: DefectMapCollection | null;
  observations?: ObservationMapCollection | null;
  routes?: RouteMapCollection | null;
  visible: LayerVisibility;
  selectedId?: string | null;
  onSelect?: (sel: MapSelection | null) => void;
  className?: string;
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

  if (fallback) return <SchematicMap {...props} />;
  return (
    <Suspense fallback={<LoadingState label="Загрузка карты…" />}>
      <MapView {...props} onFallback={onFallback} />
    </Suspense>
  );
}