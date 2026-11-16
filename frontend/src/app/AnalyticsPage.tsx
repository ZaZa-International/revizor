import {
  useAnalyticsOverview,
  useCoverage,
  useDefectsAnalytics,
  useObservationTimeBuckets,
} from '../data/hooks';
import { Badge, ErrorState, LoadingState, Status } from '../components/ui';
import { ColumnChart, CoverageGrid, HBarList, StackedBar, TimeHistogram } from '../components/charts';
import { BAND_COLORS } from '../components/map/MapView';
import { label } from '../lib/labels';
import { fmtNumber, fmtPercent } from '../lib/format';
import { useDataSource } from '../data/source';

export default function AnalyticsPage() {
  const { isDemo } = useDataSource();
  const overview = useAnalyticsOverview();
  const defects = useDefectsAnalytics();
  const coverage = useCoverage();
  const timeseries = useObservationTimeBuckets(14);

  if (overview.isPending) return <LoadingState label="Считаем агрегаты…" />;
  if (overview.error) return <ErrorState error={overview.error} onRetry={() => overview.refetch()} />;
  const o = overview.data!;

  const severityData = [1, 2, 3, 4, 5].map((s) => ({
    key: String(s),
    label: `S${s}`,
    value: o.defects_by_severity.find((x) => Number(x.key) === s)?.count ?? 0,
    color: s >= 4 ? 'var(--crit)' : s === 3 ? 'var(--warn)' : 'var(--ok)',
  }));

  return (
    <div>
      <div className="page-head">
        <div>
          <p className="eyebrow">Аналитика · {isDemo ? 'DEMO' : 'API-агрегаты'}</p>
          <h1>Состояние и покрытие</h1>
          <p className="page-desc">
            Распределения объектов и дефектов, динамика наблюдений и покрытие обследования.
            Все значения — агрегаты backend; методология отмечена у каждого блока.
          </p>
        </div>
      </div>

      <div className="analytics-grid">
        <section className="panel" aria-label="Типы объектов">
          <div className="panel-head">
            <h2 className="panel-title">Объекты по типам</h2>
            <Badge>{fmtNumber(o.assets_total)} всего</Badge>
          </div>
          <div className="panel-body">
            <HBarList
              unit="объектов"
              data={o.assets_by_type.map((t) => ({
                key: String(t.key),
                label: label.assetType(String(t.key)),
                value: t.count,
              }))}
            />
          </div>
        </section>

        <section className="panel" aria-label="Приоритеты объектов">
          <div className="panel-head">
            <h2 className="panel-title">Объекты по приоритету</h2>
          </div>
          <div className="panel-body">
            <HBarList
              unit="объектов"
              data={o.assets_by_priority_band.map((b) => ({
                key: String(b.key),
                label: label.priorityBand(String(b.key)),
                value: b.count,
                color: BAND_COLORS[String(b.key)] ?? 'var(--muted)',
              }))}
            />
            <p className="faint" style={{ fontSize: 'var(--text-micro)', marginTop: 8 }}>
              Приоритет = severity × impact × confidence (policy v1.0). Полоса NEEDS_REVIEW — низкая уверенность или неразрешённая дедупликация.
            </p>
          </div>
        </section>

        <section className="panel" aria-label="Тяжесть дефектов">
          <div className="panel-head">
            <h2 className="panel-title">Дефекты по тяжести</h2>
            {defects.data && (
              <Status tone={defects.data.open_high_severity_count > 0 ? 'crit' : 'ok'}>
                срочных (S4+, открытые): {defects.data.open_high_severity_count}
              </Status>
            )}
          </div>
          <div className="panel-body">
            <ColumnChart data={severityData} unit="дефектов" ariaLabel="Распределение дефектов по тяжести S1–S5" />
          </div>
        </section>

        <section className="panel" aria-label="Статусы дефектов">
          <div className="panel-head">
            <h2 className="panel-title">Дефекты по статусу</h2>
          </div>
          <div className="panel-body">
            <StackedBar
              ariaLabel="Распределение дефектов по статусу"
              parts={[
                { label: 'Открытые', value: o.defects_by_status.find((s) => s.key === 'OPEN')?.count ?? 0, color: 'var(--warn)' },
                { label: 'Подтверждённые', value: o.defects_by_status.find((s) => s.key === 'CONFIRMED')?.count ?? 0, color: 'var(--crit)' },
                { label: 'В работе', value: o.defects_by_status.find((s) => s.key === 'IN_PROGRESS')?.count ?? 0, color: 'var(--accent)' },
                { label: 'Устранённые', value: o.defects_by_status.find((s) => s.key === 'RESOLVED')?.count ?? 0, color: 'var(--ok)' },
                { label: 'Отклонённые', value: o.defects_by_status.find((s) => s.key === 'REJECTED')?.count ?? 0, color: 'var(--faint)' },
              ]}
            />
          </div>
        </section>

        <section className="panel" aria-label="Типы дефектов">
          <div className="panel-head">
            <h2 className="panel-title">Дефекты по типам</h2>
          </div>
          <div className="panel-body">
            {defects.isPending && <LoadingState />}
            {defects.error && <ErrorState error={defects.error} onRetry={() => defects.refetch()} />}
            {defects.data && (
              <HBarList
                unit="дефектов"
                data={defects.data.by_type.map((t) => ({
                  key: t.defect_type,
                  label: `${label.defectType(t.defect_type)}${t.avg_severity != null ? ` · ср. S${t.avg_severity.toFixed(1)}` : ''}`,
                  value: t.count,
                  color: (t.avg_severity ?? 0) >= 4 ? 'var(--crit)' : 'var(--warn)',
                }))}
              />
            )}
          </div>
        </section>

        <section className="panel" aria-label="Динамика наблюдений">
          <div className="panel-head">
            <h2 className="panel-title">Наблюдения по дням</h2>
            {timeseries.data && (
              <Badge>выборка: {fmtNumber(timeseries.data.sampleSize)} из {fmtNumber(timeseries.data.total)}</Badge>
            )}
          </div>
          <div className="panel-body">
            {timeseries.isPending && <LoadingState />}
            {timeseries.error && <ErrorState error={timeseries.error} onRetry={() => timeseries.refetch()} />}
            {timeseries.data && <TimeHistogram buckets={timeseries.data.buckets} />}
            <p className="faint" style={{ fontSize: 'var(--text-micro)', marginTop: 8 }}>
              Методология: группировка последних наблюдений по дате observed_at (до 300 записей). Не является полным историческим рядом.
            </p>
          </div>
        </section>

        <section className="panel span-2" aria-label="Покрытие обследований">
          <div className="panel-head">
            <h2 className="panel-title">Покрытие обследования</h2>
            {coverage.data && (
              <Badge tone={coverage.data.coverage_ratio > 0.1 ? 'accent' : 'warn'}>
                покрыто {fmtPercent(coverage.data.coverage_ratio, 2)} · ячейка {fmtNumber(coverage.data.grid_cell_m)} м
              </Badge>
            )}
          </div>
          <div className="panel-body">
            {coverage.isPending && <LoadingState />}
            {coverage.error && <ErrorState error={coverage.error} onRetry={() => coverage.refetch()} />}
            {coverage.data && (
              <div className="detail-grid coverage-grid">
                <CoverageGrid
                  cols={coverage.data.grid_cols}
                  rows={coverage.data.grid_rows}
                  cells={coverage.data.covered_cell_counts}
                  ariaLabel="Сетка покрытия: интенсивность — число наблюдений в ячейке"
                />
                <div>
                  <HBarList
                    unit="наблюдений"
                    data={coverage.data.routes.map((r) => ({ key: r.route_id, label: r.name, value: r.observations }))}
                  />
                  <p className="faint" style={{ fontSize: 'var(--text-micro)', marginTop: 10 }}>
                    {coverage.data.note ?? 'Эвристическая сетка покрытия по зоне обследования; не модель дорожной сети.'}
                    {' '}Ячейки без наблюдений показаны нейтрально — это пробелы покрытия, а не отсутствие проблем.
                  </p>
                </div>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}