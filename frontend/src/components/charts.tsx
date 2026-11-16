/* SVG-визуализации данных: без chart-библиотек, с осями, подписями и единицами.
   Цвет задаётся вызывающей стороной по семантике состояния. */
import { useId } from 'react';
import { fmtNumber } from '../lib/format';

export interface Datum {
  key: string;
  label: string;
  value: number;
  color?: string;
}

/* Горизонтальные бары распределения */
export function HBarList({ data, unit = 'объектов', max }: { data: Datum[]; unit?: string; max?: number }) {
  const peak = max ?? Math.max(1, ...data.map((d) => d.value));
  if (data.length === 0) return <p className="muted small">Нет данных для распределения.</p>;
  return (
    <div role="img" aria-label={`Распределение, ${unit}: ${data.map((d) => `${d.label} ${d.value}`).join(', ')}`}>
      {data.map((d) => (
        <div key={d.key} style={{ display: 'grid', gridTemplateColumns: 'minmax(88px, 160px) minmax(0, 1fr) auto', gap: 'var(--sp-3)', alignItems: 'center', padding: '5px 0' }}>
          <span className="small" style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }} title={d.label}>
            {d.label}
          </span>
          <span style={{ height: 10, background: 'var(--raised)', borderRadius: 2, overflow: 'hidden' }}>
            <span
              style={{
                display: 'block',
                height: '100%',
                width: `${(d.value / peak) * 100}%`,
                background: d.color ?? 'var(--accent)',
                borderRadius: 2,
                transition: 'width var(--dur-swap) var(--ease-out)',
              }}
            />
          </span>
          <span className="num small" style={{ minWidth: 44, textAlign: 'right' }}>
            {fmtNumber(d.value)}
          </span>
        </div>
      ))}
      <p className="faint" style={{ fontSize: 'var(--text-micro)', marginTop: 6 }}>
        единицы: {unit}
      </p>
    </div>
  );
}

/* Вертикальная гистограмма с осью Y */
export function ColumnChart({
  data,
  height = 160,
  unit,
  ariaLabel,
}: {
  data: Datum[];
  height?: number;
  unit?: string;
  ariaLabel: string;
}) {
  const gid = useId();
  const peak = Math.max(1, ...data.map((d) => d.value));
  const ticks = [0, 0.5, 1].map((t) => Math.round(peak * t));
  const w = 100;
  const gl = 12;
  const plotW = w - gl;
  const bw = plotW / Math.max(1, data.length);
  return (
    <figure style={{ margin: 0 }}>
      <svg viewBox={`0 0 ${w} ${height}`} style={{ width: '100%', height }} role="img" aria-label={ariaLabel} preserveAspectRatio="none">
        {ticks.map((t, i) => {
          const y = height - 22 - (t / peak) * (height - 34);
          return (
            <g key={i}>
              <line x1={gl} x2={w} y1={y} y2={y} stroke="var(--line-soft)" strokeWidth={0.4} />
              <text x={gl - 2} y={y - 1.5} fontSize={4.4} fill="var(--faint)" fontFamily="var(--font-mono)" textAnchor="end">
                {fmtNumber(t)}
              </text>
            </g>
          );
        })}
        {data.map((d, i) => {
          const h = (d.value / peak) * (height - 34);
          const x = gl + i * bw + bw * 0.18;
          return (
            <g key={`${gid}-${d.key}`}>
              <rect x={x} y={height - 22 - h} width={bw * 0.64} height={Math.max(0.5, h)} fill={d.color ?? 'var(--accent)'} rx={0.8} />
              <text x={gl + i * bw + bw / 2} y={height - 12} fontSize={4.6} fill="var(--muted)" textAnchor="middle" fontFamily="var(--font-mono)">
                {d.label}
              </text>
              <text x={gl + i * bw + bw / 2} y={height - 25 - h} fontSize={4.6} fill="var(--ink)" textAnchor="middle" fontFamily="var(--font-mono)">
                {d.value > 0 ? fmtNumber(d.value) : ''}
              </text>
            </g>
          );
        })}
      </svg>
      {unit && (
        <figcaption className="faint" style={{ fontSize: 'var(--text-micro)', marginTop: 4 }}>
          единицы: {unit}
        </figcaption>
      )}
    </figure>
  );
}

/* Sparkline (тренд без осей, для компактных сводок) */
export function Sparkline({
  values,
  width = 120,
  height = 32,
  color = 'var(--accent)',
  ariaLabel,
}: {
  values: number[];
  width?: number;
  height?: number;
  color?: string;
  ariaLabel: string;
}) {
  if (values.length < 2) return <span className="faint small">—</span>;
  const peak = Math.max(1, ...values);
  const pts = values.map((v, i) => `${(i / (values.length - 1)) * width},${height - 3 - (v / peak) * (height - 6)}`);
  return (
    <svg width={width} height={height} role="img" aria-label={ariaLabel}>
      <polyline points={pts.join(' ')} fill="none" stroke={color} strokeWidth={1.6} strokeLinejoin="round" />
      <circle cx={pts[pts.length - 1].split(',')[0]} cy={pts[pts.length - 1].split(',')[1]} r={2.2} fill={color} />
    </svg>
  );
}

/* Составная полоса (доли целого) */
export function StackedBar({ parts, ariaLabel }: { parts: { label: string; value: number; color: string }[]; ariaLabel: string }) {
  const total = parts.reduce((s, p) => s + p.value, 0);
  if (total === 0) return <p className="muted small">Нет данных.</p>;
  return (
    <div>
      <div role="img" aria-label={ariaLabel} style={{ display: 'flex', height: 14, borderRadius: 3, overflow: 'hidden', background: 'var(--raised)' }}>
        {parts.map(
          (p) =>
            p.value > 0 && (
              <span key={p.label} style={{ width: `${(p.value / total) * 100}%`, background: p.color }} title={`${p.label}: ${p.value}`} />
            ),
        )}
      </div>
      <div className="legend" style={{ marginTop: 8 }}>
        {parts.map((p) => (
          <span key={p.label} className="legend-item">
            <i className="legend-swatch" style={{ background: p.color }} />
            {p.label} <span className="num">{fmtNumber(p.value)}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

/* Сетка покрытия обследований (heatmap по ячейкам) */
export function CoverageGrid({
  cols,
  rows,
  cells,
  ariaLabel,
}: {
  cols: number;
  rows: number;
  cells: { cx: number; cy: number; observations: number }[];
  ariaLabel: string;
}) {
  const peak = Math.max(1, ...cells.map((c) => c.observations));
  const map = new Map(cells.map((c) => [`${c.cx},${c.cy}`, c.observations]));
  const cw = 10;
  const w = cols * cw;
  const h = rows * cw;
  return (
    <svg viewBox={`0 0 ${w} ${h}`} style={{ width: '100%', maxHeight: 320 }} role="img" aria-label={ariaLabel}>
      {Array.from({ length: rows }, (_, cy) =>
        Array.from({ length: cols }, (_, cx) => {
          const n = map.get(`${cx},${cy}`) ?? 0;
          const alpha = n === 0 ? 0 : 0.25 + 0.75 * (n / peak);
          return (
            <rect
              key={`${cx}-${cy}`}
              x={cx * cw + 0.5}
              y={(rows - 1 - cy) * cw + 0.5}
              width={cw - 1}
              height={cw - 1}
              rx={1}
              fill={n === 0 ? 'var(--raised)' : `rgba(117, 215, 204, ${alpha})`}
            >
              <title>{`ячейка ${cx},${cy}: ${n} наблюдений`}</title>
            </rect>
          );
        }),
      )}
    </svg>
  );
}

/* Временная гистограмма наблюдений по дням */
export function TimeHistogram({
  buckets,
  height = 150,
}: {
  buckets: { label: string; value: number }[];
  height?: number;
}) {
  const data: Datum[] = buckets.map((b) => ({ key: b.label, label: b.label, value: b.value, color: 'var(--accent)' }));
  return <ColumnChart data={data} height={height} unit="наблюдений в день" ariaLabel="Наблюдения по дням" />;
}