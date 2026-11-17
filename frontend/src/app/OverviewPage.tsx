import { Link, useNavigate } from 'react-router-dom';
import {
  useAnalyticsOverview,
  useAssets,
  useDefects,
  useJobs,
  useMapAssets,
  useMapRoutes,
  useObservations,
} from '../data/hooks';
import { DemoBanner, ErrorState, LoadingState, Progress, Severity, Status } from '../components/ui';
import { StackedBar } from '../components/charts';
import NetworkMap from '../components/map/NetworkMap';
import { assetTypeIcon, IconArrowRight, IconDefect } from '../components/icons';
import { label, bandTone, jobStatusTone, reviewStatusTone } from '../lib/labels';
import { fmtDateTime, fmtNumber, fmtPercent, fmtRelative } from '../lib/format';
import { useDataSource } from '../data/source';

export default function OverviewPage() {
  const navigate = useNavigate();
  const { isDemo } = useDataSource();
  const overview = useAnalyticsOverview();
  const highAssets = useAssets({ priority_band: 'HIGH_PRIORITY', sort_by: 'current_priority', order: 'desc', page_size: 5 });
  const criticalDefects = useDefects({ severity_min: 4, sort_by: 'severity', order: 'desc', page_size: 5 });
  const recent = useObservations({ page_size: 6 });
  const queue = useObservations({ review_status: 'UNREVIEWED', page_size: 1 });
  const jobs = useJobs({ page_size: 4 });
  const mapAssets = useMapAssets({ limit: 500 });
  const mapRoutes = useMapRoutes();

  if (overview.isPending) return <LoadingState label="Собираем сводку по инфраструктуре…" />;
  if (overview.error) return <ErrorState error={overview.error} onRetry={() => overview.refetch()} />;
  const o = overview.data!;
  const openDefects = o.defects_by_status.filter((s) => ['OPEN', 'CONFIRMED', 'IN_PROGRESS'].includes(String(s.key))).reduce((a, b) => a + b.count, 0);

  return (
    <div>
      <div className="page-head">
        <div>
          <p className="eyebrow">Обзор · {isDemo ? 'демо-данные' : 'данные API'}</p>
          <h1>Состояние инфраструктуры</h1>
          <p className="page-desc">
            Что требует внимания прямо сейчас: приоритетные объекты, открытые дефекты и очередь проверки.
          </p>
        </div>
        <div className="page-head-actions">
          <Link className="btn" to="/app/map">
            Карта сети
          </Link>
          <Link className="btn btn-primary" to="/app/reviews">
            Очередь проверки {(queue.data?.total ?? 0) > 0 && <span className="num">· {queue.data?.total}</span>}
          </Link>
        </div>
      </div>

      <div className="kpi-strip">
        <div className="kpi">
          <span className="kpi-label">Объекты в реестре</span>
          <span className="kpi-value">{fmtNumber(o.assets_total)}</span>
          <span className="kpi-sub">без координат: {fmtNumber(o.assets_without_location)}</span>
        </div>
        <div className="kpi">
          <span className="kpi-label">Наблюдения</span>
          <span className="kpi-value">{fmtNumber(o.observations_total)}</span>
          <span className="kpi-sub">проверено: {fmtPercent(o.observations_reviewed_ratio, 0)}</span>
        </div>
        <div className="kpi">
          <span className="kpi-label">Дефекты</span>
          <span className="kpi-value">{fmtNumber(o.defects_total)}</span>
          <span className="kpi-sub">открытых: {fmtNumber(openDefects)}</span>
        </div>
        <div className="kpi">
          <span className="kpi-label">Очередь проверки</span>
          <span className="kpi-value" style={{ color: (queue.data?.total ?? 0) > 0 ? 'var(--warn)' : 'var(--ok)' }}>
            {fmtNumber(queue.data?.total ?? 0)}
          </span>
          <span className="kpi-sub">ожидают решения оператора</span>
        </div>
      </div>

      <div className="overview-grid" style={{ marginBottom: 'var(--sp-5)' }}>
        <section className="panel" aria-label="Объекты высокого приоритета">
          <div className="panel-head">
            <h2 className="panel-title">Требуют внимания</h2>
            <Link className="link small" to="/app/assets?priority_band=HIGH_PRIORITY">
              все объекты
            </Link>
          </div>
          <div className="attention-list">
            {highAssets.isPending && <LoadingState />}
            {highAssets.error && <ErrorState error={highAssets.error} onRetry={() => highAssets.refetch()} />}
            {highAssets.data?.items.length === 0 && (
              <p className="muted small" style={{ padding: 'var(--sp-5)' }}>
                Объектов высокого приоритета нет.
              </p>
            )}
            {highAssets.data?.items.map((a) => {
              const Icon = assetTypeIcon(a.asset_type);
              return (
                <Link key={a.id} to={`/app/assets/${a.id}`} className="attention-item">
                  <Icon style={{ color: 'var(--crit)' }} />
                  <span className="att-main">
                    <span className="att-title">{a.display_name ?? a.external_id ?? a.id}</span>
                    <span className="att-sub">
                      {label.assetType(a.asset_type)} · {label.condition(a.current_condition)} · осмотр {fmtRelative(a.last_observed_at)}
                    </span>
                  </span>
                  <span className="num" title="Текущий приоритет (0–100)">
                    {fmtNumber(a.current_priority, 0)}
                  </span>
                  <Status tone={bandTone[a.priority_band ?? ''] ?? 'neutral'}>{label.priorityBand(a.priority_band)}</Status>
                </Link>
              );
            })}
          </div>
        </section>

        <section className="panel" aria-label="Критические дефекты">
          <div className="panel-head">
            <h2 className="panel-title">Дефекты S4–S5</h2>
            <Link className="link small" to="/app/defects?severity_min=4">
              все дефекты
            </Link>
          </div>
          <div className="attention-list">
            {criticalDefects.isPending && <LoadingState />}
            {criticalDefects.error && <ErrorState error={criticalDefects.error} onRetry={() => criticalDefects.refetch()} />}
            {criticalDefects.data?.items.length === 0 && (
              <p className="muted small" style={{ padding: 'var(--sp-5)' }}>
                Критических дефектов не зарегистрировано.
              </p>
            )}
            {criticalDefects.data?.items.map((d) => (
              <Link key={d.id} to={`/app/defects/${d.id}`} className="attention-item">
                <IconDefect style={{ color: 'var(--crit)' }} />
                <span className="att-main">
                  <span className="att-title">{label.defectType(d.defect_type)}</span>
                  <span className="att-sub">
                    {label.defectStatus(d.status)} · замечен {fmtRelative(d.last_detected_at)}
                  </span>
                </span>
                <Severity value={d.severity} />
              </Link>
            ))}
          </div>
        </section>
      </div>

      <div className="overview-grid">
        <section className="panel" aria-label="Карта объектов">
          <div className="panel-head">
            <h2 className="panel-title">Карта сети</h2>
            <Link className="link small" to="/app/map">
              открыть карту <IconArrowRight className="icon-sm" style={{ display: 'inline', verticalAlign: '-2px' }} />
            </Link>
          </div>
          <div className="overview-map">
            <NetworkMap
              assets={mapAssets.data ?? null}
              routes={mapRoutes.data ?? null}
              visible={{ assets: true, defects: false, observations: false, routes: true }}
              onSelect={(sel) => {
                if (sel?.layer === 'assets') navigate(`/app/assets/${sel.id}`);
                if (sel?.layer === 'routes') navigate(`/app/routes/${sel.id}`);
              }}
            />
          </div>
        </section>

        <section className="panel" aria-label="Последние наблюдения">
          <div className="panel-head">
            <h2 className="panel-title">Последние наблюдения</h2>
            <Link className="link small" to="/app/observations">
              все
            </Link>
          </div>
          <div className="attention-list">
            {recent.isPending && <LoadingState />}
            {recent.error && <ErrorState error={recent.error} onRetry={() => recent.refetch()} />}
            {recent.data?.items.map((obs) => (
              <Link key={obs.id} to={`/app/observations/${obs.id}`} className="attention-item">
                <span className="att-main">
                  <span className="att-title">
                    {label.assetType(obs.object_type)} · {label.condition(obs.effective_condition ?? obs.condition_class)}
                  </span>
                  <span className="att-sub">{fmtDateTime(obs.observed_at)}</span>
                </span>
                <Status tone={reviewStatusTone[obs.review_status] ?? 'neutral'} shape="square">
                  {label.reviewStatus(obs.review_status)}
                </Status>
              </Link>
            ))}
          </div>
        </section>
      </div>

      <div className="overview-grid" style={{ marginTop: 'var(--sp-5)' }}>
        <section className="panel" aria-label="Ход проверки">
          <div className="panel-head">
            <h2 className="panel-title">Ход проверки наблюдений</h2>
            {isDemo && <DemoBanner compact />}
          </div>
          <div className="panel-body">
            <StackedBar
              ariaLabel="Доля проверенных и непроверенных наблюдений"
              parts={[
                { label: 'Проверено', value: o.observations_reviewed, color: 'var(--ok)' },
                { label: 'Ожидают проверки', value: Math.max(0, o.observations_total - o.observations_reviewed), color: 'var(--warn)' },
              ]}
            />
            <p className="faint small" style={{ marginTop: 'var(--sp-3)' }}>
              Проверка оператором (human-in-the-loop): каждое решение сохраняется в append-only истории review.
            </p>
          </div>
        </section>

        <section className="panel" aria-label="Последние задачи обработки">
          <div className="panel-head">
            <h2 className="panel-title">Задачи обработки</h2>
            <Link className="link small" to="/app/jobs">
              все задачи
            </Link>
          </div>
          <div className="attention-list">
            {jobs.isPending && <LoadingState />}
            {jobs.error && <ErrorState error={jobs.error} onRetry={() => jobs.refetch()} />}
            {jobs.data?.items.length === 0 && (
              <p className="muted small" style={{ padding: 'var(--sp-5)' }}>
                Задач пока нет. Загрузите материалы в разделе «Задачи».
              </p>
            )}
            {jobs.data?.items.map((j) => (
              <Link key={j.id} to={`/app/jobs/${j.id}`} className="attention-item" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 6 }}>
                <span style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}>
                  <span className="mono small">{j.id.slice(0, 8)}</span>
                  <Status tone={jobStatusTone[j.status] ?? 'neutral'}>{label.jobStatus(j.status)}</Status>
                </span>
                <Progress value={j.progress} tone={j.status === 'FAILED' ? 'crit' : j.status === 'PARTIALLY_COMPLETED' ? 'warn' : undefined} />
                <span className="att-sub">
                  кадры: {fmtNumber(j.processed_frames)}/{fmtNumber(j.total_frames)} · {fmtDateTime(j.created_at)}
                </span>
              </Link>
            ))}
          </div>
        </section>
      </div>
    </div>
  );
}