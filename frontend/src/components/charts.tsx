/* SVG/HTML-визуализации данных: без chart-библиотек, с осями, подписями и единицами.
   Цвет задаётся вызывающей стороной по семантике состояния.
   Подписи — обычный HTML-текст (не масштабируются вместе с графиком). */
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

/* Вертикальная гистограмма: ось Y от нуля, HTML-подписи нормального кегля */
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
  if (data.length === 0) return <p className="muted small">Нет данных.</p>;
  const total = data.reduce((s, d) => s + d.value, 0);
  if (total === 0) return <p className="muted small">Нет данных за период.</p>;
  const peak = Math.max(1, ...data.map((d) => d.value));
  const ticks = [1, 0.5, 0].map((t) => ({ pct: t * 100, value: Math.round(peak * t) }));
  const labelEvery = data.length > 12 ? 2 : 1;
  return (
    <figure style={{ margin: 0 }}>
      <div className="col-chart" role="img" aria-label={ariaLabel}>
        <div className="col-chart-yaxis" style={{ height: height - 16 }} aria-hidden>
          {ticks.map((t) => (
            <span key={t.pct} className="col-chart-tick num" style={{ bottom: `${t.pct}%` }}>
              {fmtNumber(t.value)}
            </span>
          ))}
        </div>
        <div className="col-chart-area" style={{ height: height - 16 }}>
          {ticks.map((t) => (
            <i key={t.pct} className="col-chart-gridline" style={{ bottom: `${t.pct}%` }} aria-hidden />
          ))}
          <div className="col-chart-bars">
            {data.map((d) => {
              const pct = (d.value / peak) * 100;
              return (
                <div key={d.key} className="col-chart-barwrap" title={`${d.label}: ${fmtNumber(d.value)}`}>
                  {d.value > 0 && (
                    <span className="col-chart-val num" style={{ bottom: `calc(${pct}% + 3px)` }}>
                      {fmtNumber(d.value)}
                    </span>
                  )}
                  <i className="col-chart-bar" style={{ height: `${pct}%`, background: d.color ?? 'var(--accent)' }} />
                </div>
              );
            })}
          </div>
        </div>
        <div className="col-chart-xaxis" aria-hidden>
          {data.map((d, i) => (
            <span key={d.key} className="col-chart-xlabel mono">
              {i % labelEvery === 0 ? d.label : ''}
            </span>
          ))}
        </div>
      </div>
      {unit && (
        <figcaption className="faint" style={{ fontSize: 'var(--text-micro)', marginTop: 4 }}>
          единицы: {unit}
        </figcaption>
      )}
    </figure>
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
              fill={n === 0 ? 'var(--raised)' : 'var(--accent)'}
              fillOpacity={n === 0 ? 1 : alpha}
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