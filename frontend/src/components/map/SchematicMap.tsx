/* Интерактивная SVG-схема: fallback при отказе WebGL/тайлов.
   Та же геометрия данных, координатная сетка вместо базовой карты.
   Никакой выдуманной географии — только проекция реальных координат. */
import { useMemo, useRef, useState, useCallback } from 'react';
import type {
  AssetMapCollection,
  DefectMapCollection,
  ObservationMapCollection,
  RouteMapCollection,
} from '../../api/types';
import { BAND_COLORS, type LayerVisibility, type MapSelection } from './MapView';
import { IconMinus, IconPlus, IconTarget } from '../icons';

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

const W = 1000;
const H = 680;
const PAD = 56;

export default function SchematicMap({ assets, defects, observations, routes, visible, selectedId, onSelect, className }: Props) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number; px: number; py: number } | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const bounds = useMemo(() => {
    const pts: [number, number][] = [];
    const collect = (fc?: { features: { geometry: { type: 'Point'; coordinates: number[] } | { type: 'LineString'; coordinates: number[][] } | null }[] } | null) => {
      fc?.features.forEach((f) => {
        const g = f.geometry;
        if (!g) return;
        if (g.type === 'Point') pts.push([g.coordinates[0], g.coordinates[1]]);
        else g.coordinates.forEach((c) => pts.push([c[0], c[1]]));
      });
    };
    collect(assets);
    collect(defects);
    collect(observations);
    collect(routes);
    if (pts.length === 0) return { minLon: 37.55, maxLon: 37.7, minLat: 55.7, maxLat: 55.8 };
    const lons = pts.map((p) => p[0]);
    const lats = pts.map((p) => p[1]);
    const dLon = Math.max(0.004, Math.max(...lons) - Math.min(...lons));
    const dLat = Math.max(0.003, Math.max(...lats) - Math.min(...lats));
    return {
      minLon: Math.min(...lons) - dLon * 0.12,
      maxLon: Math.max(...lons) + dLon * 0.12,
      minLat: Math.min(...lats) - dLat * 0.12,
      maxLat: Math.max(...lats) + dLat * 0.12,
    };
  }, [assets, defects, observations, routes]);

  const proj = useCallback(
    (lon: number, lat: number): [number, number] => {
      const x = PAD + ((lon - bounds.minLon) / (bounds.maxLon - bounds.minLon)) * (W - PAD * 2);
      const y = H - PAD - ((lat - bounds.minLat) / (bounds.maxLat - bounds.minLat)) * (H - PAD * 2);
      return [x, y];
    },
    [bounds],
  );

  const vbW = W / zoom;
  const vbH = H / zoom;
  const vbX = (W - vbW) / 2 + pan.x;
  const vbY = (H - vbH) / 2 + pan.y;

  const gridLines = useMemo(() => {
    const lines: { x1: number; y1: number; x2: number; y2: number; label: string; lx: number; ly: number }[] = [];
    for (let i = 0; i <= 4; i++) {
      const lon = bounds.minLon + ((bounds.maxLon - bounds.minLon) * i) / 4;
      const [x] = proj(lon, bounds.minLat);
      lines.push({ x1: x, y1: PAD / 2, x2: x, y2: H - PAD / 2, label: lon.toFixed(3), lx: x + 4, ly: H - PAD / 2 + 16 });
    }
    for (let i = 0; i <= 3; i++) {
      const lat = bounds.minLat + ((bounds.maxLat - bounds.minLat) * i) / 3;
      const [, y] = proj(bounds.minLon, lat);
      lines.push({ x1: PAD / 2, y1: y, x2: W - PAD / 2, y2: y, label: lat.toFixed(3), lx: PAD / 2 - 4, ly: y - 5 });
    }
    return lines;
  }, [bounds, proj]);

  const select = (layer: MapSelection['layer'], f: { properties?: Record<string, unknown> | null; geometry: { type: 'Point'; coordinates: number[] } | { type: 'LineString'; coordinates: number[][] } | null }) => {
    const coords = f.geometry?.type === 'Point' ? [f.geometry.coordinates[0], f.geometry.coordinates[1]] : [bounds.minLon, bounds.minLat];
    onSelect?.({
      layer,
      id: String(f.properties?.id ?? ''),
      properties: (f.properties ?? {}) as Record<string, unknown>,
      lon: coords[0],
      lat: coords[1],
    });
  };

  return (
    <div className={className} style={{ position: 'relative', width: '100%', height: '100%', minHeight: 280, background: 'var(--bg)' }}>
      <svg
        ref={svgRef}
        viewBox={`${vbX} ${vbY} ${vbW} ${vbH}`}
        style={{ width: '100%', height: '100%', touchAction: 'none', cursor: drag.current ? 'grabbing' : 'grab' }}
        role="application"
        aria-label="Схематичная карта инфраструктуры"
        onWheel={(e) => {
          e.preventDefault();
          setZoom((z) => Math.max(0.7, Math.min(8, z * (e.deltaY < 0 ? 1.18 : 0.85))));
        }}
        onPointerDown={(e) => {
          drag.current = { x: e.clientX, y: e.clientY, px: pan.x, py: pan.y };
          (e.target as Element).setPointerCapture?.(e.pointerId);
        }}
        onPointerMove={(e) => {
          if (!drag.current || !svgRef.current) return;
          const rect = svgRef.current.getBoundingClientRect();
          const scale = vbW / rect.width;
          setPan({
            x: drag.current.px - (e.clientX - drag.current.x) * scale,
            y: drag.current.py - (e.clientY - drag.current.y) * scale,
          });
        }}
        onPointerUp={() => {
          drag.current = null;
        }}
      >
        <rect x={vbX} y={vbY} width={vbW} height={vbH} fill="var(--bg)" />
        {gridLines.map((l, i) => (
          <g key={i}>
            <line x1={l.x1} y1={l.y1} x2={l.x2} y2={l.y2} stroke="var(--line-soft)" strokeWidth={1} />
            <text x={l.lx} y={l.ly} fontSize={12} fill="var(--faint)" fontFamily="var(--font-mono)" textAnchor={l.x1 === l.x2 ? 'start' : 'end'}>
              {l.label}
            </text>
          </g>
        ))}

        {visible.routes &&
          routes?.features.map((f) => {
            if (!f.geometry || f.geometry.type !== 'LineString') return null;
            const pts = f.geometry.coordinates.map((c) => proj(c[0], c[1]).join(',')).join(' ');
            const sel = selectedId === f.properties?.id;
            return (
              <polyline
                key={String(f.properties?.id)}
                points={pts}
                fill="none"
                stroke={sel ? 'var(--ink)' : 'var(--accent-dim)'}
                strokeWidth={sel ? 3.4 : 2.4}
                strokeLinecap="round"
                strokeLinejoin="round"
                opacity={0.9}
                style={{ cursor: 'pointer' }}
                onClick={() => select('routes', f as never)}
              />
            );
          })}

        {visible.observations &&
          observations?.features.map((f) => {
            if (!f.geometry || f.geometry.type !== 'Point') return null;
            const [x, y] = proj(f.geometry.coordinates[0], f.geometry.coordinates[1]);
            const unreviewed = f.properties?.review_status === 'UNREVIEWED';
            return (
              <circle
                key={String(f.properties?.id)}
                cx={x}
                cy={y}
                r={4}
                fill={unreviewed ? 'var(--warn)' : 'var(--accent)'}
                opacity={0.7}
                stroke="var(--bg)"
                strokeWidth={1}
                style={{ cursor: 'pointer' }}
                onClick={() => select('observations', f as never)}
              />
            );
          })}

        {visible.defects &&
          defects?.features.map((f) => {
            if (!f.geometry || f.geometry.type !== 'Point') return null;
            const [x, y] = proj(f.geometry.coordinates[0], f.geometry.coordinates[1]);
            const sev = Number(f.properties?.severity ?? 3);
            return (
              <circle
                key={String(f.properties?.id)}
                cx={x}
                cy={y}
                r={12}
                fill="none"
                stroke={sev >= 4 ? 'var(--crit)' : 'var(--warn)'}
                strokeWidth={2}
                style={{ cursor: 'pointer' }}
                onClick={() => select('defects', f as never)}
              />
            );
          })}

        {visible.assets &&
          assets?.features.map((f) => {
            if (!f.geometry || f.geometry.type !== 'Point') return null;
            const [x, y] = proj(f.geometry.coordinates[0], f.geometry.coordinates[1]);
            const band = String(f.properties?.priority_band ?? 'NEEDS_REVIEW');
            const sel = selectedId === f.properties?.id;
            const name = String(f.properties?.display_name ?? 'Объект');
            return (
              <g
                key={String(f.properties?.id)}
                role="button"
                tabIndex={0}
                aria-label={name}
                style={{ cursor: 'pointer', outline: 'none' }}
                onClick={() => select('assets', f as never)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' || e.key === ' ') {
                    e.preventDefault();
                    select('assets', f as never);
                  }
                }}
              >
                {sel && <circle cx={x} cy={y} r={16} fill="var(--accent)" fillOpacity={0.15} stroke="var(--ink)" strokeWidth={2} />}
                <circle cx={x} cy={y} r={7} fill={BAND_COLORS[band] ?? BAND_COLORS.NEEDS_REVIEW} stroke="var(--bg)" strokeWidth={2} />
                <title>{name}</title>
              </g>
            );
          })}
      </svg>
      <div style={{ position: 'absolute', top: 10, left: 12 }} className="badge">
        Схематичный режим · без базовой карты
      </div>
      <div style={{ position: 'absolute', top: 10, right: 12, display: 'flex', flexDirection: 'column', gap: 6 }}>
        <button className="btn btn-sm" aria-label="Приблизить" onClick={() => setZoom((z) => Math.min(8, z * 1.3))}><IconPlus className="icon-sm" /></button>
        <button className="btn btn-sm" aria-label="Отдалить" onClick={() => setZoom((z) => Math.max(0.7, z / 1.3))}><IconMinus className="icon-sm" /></button>
        <button className="btn btn-sm" aria-label="Сбросить вид" onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}><IconTarget className="icon-sm" /></button>
      </div>
    </div>
  );
}