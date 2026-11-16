/* deck.gl integration: HexagonLayer агрегация дефектов поверх MapLibre.
   Interleaved mode — общий WebGL2-контекст с картой (один контекст на карту).
   Модуль грузится динамически только при включении агрегации. */

import { MapLibreOverlay } from '@deck.gl/maplibre';
import { HexagonLayer } from '@deck.gl/aggregation-layers';
import type { Map as MLMap } from 'maplibre-gl';

export interface HexbinPoint {
  position: [number, number];
  severity: number;
}

export interface DeckData {
  defects: HexbinPoint[];
  extruded: boolean;
}

export interface DeckHandle {
  update(data: DeckData): void;
  dispose(): void;
}

const COLOR_RANGE: [number, number, number][] = [
  [26, 48, 56],
  [61, 138, 129],
  [117, 215, 204],
  [240, 164, 92],
  [230, 108, 97],
];

export function createDeckOverlay(map: MLMap): DeckHandle | null {
  const gl = (map as unknown as { painter?: { context?: { gl?: unknown } } }).painter?.context?.gl;
  if (typeof WebGL2RenderingContext === 'undefined' || !(gl instanceof WebGL2RenderingContext)) {
    return null;
  }
  const beforeId = map.getStyle().layers?.find((l) => l.type === 'symbol')?.id;
  const overlay = new MapLibreOverlay({ interleaved: true, layers: [] });
  map.addControl(overlay);

  let lastData: DeckData = { defects: [], extruded: false };

  const buildLayers = (data: DeckData) =>
    data.defects.length === 0
      ? []
      : [
          new HexagonLayer<HexbinPoint>({
            id: 'revizor-defect-hexbin',
            data: data.defects,
            getPosition: (d: HexbinPoint) => d.position,
            radius: 150,
            coverage: 0.85,
            extruded: data.extruded,
            elevationScale: 6,
            getElevationWeight: 1,
            getColorWeight: (d: HexbinPoint) => d.severity,
            colorRange: COLOR_RANGE,
            opacity: 0.55,
            pickable: false,
            beforeId,
          } as unknown as ConstructorParameters<typeof HexagonLayer>[0]),
        ];

  const apply = () => {
    overlay.setProps({ interleaved: true, layers: buildLayers(lastData) });
  };

  const ensure = () => {
    const attached = map.getLayersOrder().some((id) => id.startsWith('deck-maplibre-layer-group'));
    if (!attached && lastData.defects.length > 0) apply();
  };
  map.on('idle', ensure);

  const update = (data: DeckData) => {
    lastData = data;
    apply();
  };

  const dispose = () => {
    map.off('idle', ensure);
    try {
      map.removeControl(overlay);
    } catch {
      /* карта уже могла быть удалена */
    }
  };

  return { update, dispose };
}
