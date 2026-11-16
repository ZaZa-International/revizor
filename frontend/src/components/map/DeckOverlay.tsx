import { useEffect, useMemo, useRef } from 'react';
import type { Map as MLMap } from 'maplibre-gl';
import type { GeoFeature, MapMode } from '../../geo/types';
import type { DeckHandle } from '../../geo/deck';

interface Props {
  map: MLMap | null;
  enabled: boolean;
  defects: GeoFeature[];
  mode: MapMode;
  onUnavailable?: () => void;
}

export default function DeckOverlay({ map, enabled, defects, mode, onUnavailable }: Props) {
  const handleRef = useRef<DeckHandle | null>(null);
  const unavailableRef = useRef(onUnavailable);
  unavailableRef.current = onUnavailable;

  const data = useMemo(
    () =>
      defects
        .filter((f) => f.geometry.type === 'Point')
        .map((f) => ({
          position: (f.geometry as GeoJSON.Point).coordinates as [number, number],
          severity: Number(f.domain.severity ?? 1),
        })),
    [defects],
  );

  useEffect(() => {
    if (!map || !enabled) {
      handleRef.current?.dispose();
      handleRef.current = null;
      return;
    }
    let cancelled = false;
    const create = () => {
      import('../../geo/deck')
        .then((mod) => {
          if (cancelled) return;
          if (!handleRef.current) {
            const handle = mod.createDeckOverlay(map);
            if (!handle) {
              unavailableRef.current?.();
              return;
            }
            handleRef.current = handle;
          }
          handleRef.current.update({ defects: data, extruded: mode === '3d' });
        })
        .catch(() => unavailableRef.current?.());
    };
    create();
    return () => {
      cancelled = true;
    };
  }, [map, enabled, data, mode]);

  useEffect(
    () => () => {
      handleRef.current?.dispose();
      handleRef.current = null;
    },
    [],
  );

  return null;
}
