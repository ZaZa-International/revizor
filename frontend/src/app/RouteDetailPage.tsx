import { Link, useParams } from 'react-router-dom';
import { useJobs, useMapRoutes, useObservations, useRoute } from '../data/hooks';
import { Badge, ErrorState, KeyValue, LoadingState, Status } from '../components/ui';
import NetworkMap from '../components/map/NetworkMap';
import { IconChevronLeft } from '../components/icons';
import { jobStatusTone, label } from '../lib/labels';
import { fmtDateTime, fmtDistance, fmtNumber } from '../lib/format';

export default function RouteDetailPage() {
  const { id } = useParams<{ id: string }>();
  const route = useRoute(id);
  const mapRoutes = useMapRoutes();
  const jobs = useJobs({ route_id: id, page_size: 10 });
  const routeJobIds = jobs.data?.items.map((j) => j.id) ?? [];
  const observations = useObservations({ job_id: routeJobIds[0], page_size: 1 });

  if (route.isPending) return <LoadingState label="Загрузка маршрута…" />;
  if (route.error) return <ErrorState error={route.error} onRetry={() => route.refetch()} />;
  const r = route.data!;
  const trackPoints = (r.track_geojson?.coordinates as [number, number][] | undefined)?.length ?? 0;

  return (
    <div>
      <div className="page-head">
        <div>
          <Link className="link small" to="/app/routes">
            <IconChevronLeft className="icon-sm" style={{ display: 'inline', verticalAlign: '-2px' }} /> Маршруты
          </Link>
          <h1 style={{ marginTop: 8 }}>{r.name}</h1>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 10 }}>
            {r.vehicle_id && <Badge>авто: {r.vehicle_id}</Badge>}
            <Badge>дистанция: {fmtDistance(r.total_distance_m)}</Badge>
            <Badge>точек трека: {fmtNumber(trackPoints)}</Badge>
          </div>
        </div>
      </div>

      <div className="detail-grid">
        <section className="panel" aria-label="Трек маршрута">
          <div className="panel-head">
            <h2 className="panel-title">Трек</h2>
            <Link className="link small" to="/app/map">общая карта</Link>
          </div>
          <div className="detail-map" style={{ height: 340 }}>
            <NetworkMap
              routes={mapRoutes.data ?? null}
              visible={{ assets: false, defects: false, observations: false, routes: true }}
              selectedId={r.id}
            />
          </div>
        </section>

        <section className="panel" aria-label="Параметры маршрута">
          <div className="panel-head">
            <h2 className="panel-title">Параметры</h2>
          </div>
          <div className="panel-body">
            <KeyValue
              items={[
                ['Идентификатор', <span className="mono small">{r.id}</span>],
                ['Начало', fmtDateTime(r.started_at)],
                ['Завершение', fmtDateTime(r.finished_at)],
                ['Дистанция', fmtDistance(r.total_distance_m)],
                ['Создан', fmtDateTime(r.created_at)],
              ]}
            />
            <hr className="divider" />
            <p className="eyebrow" style={{ marginBottom: 10 }}>Задачи маршрута</p>
            {jobs.isPending && <LoadingState />}
            {jobs.data && jobs.data.items.length === 0 && (
              <p className="muted small">Задач обработки по маршруту нет.</p>
            )}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {jobs.data?.items.map((j) => (
                <Link key={j.id} to={`/app/jobs/${j.id}`} className="layer-toggle" style={{ textDecoration: 'none' }}>
                  <span className="mono small">{j.id.slice(0, 8)}</span>
                  <Status tone={jobStatusTone[j.status] ?? 'neutral'}>{label.jobStatus(j.status)}</Status>
                </Link>
              ))}
            </div>
            {observations.data && observations.data.total > 0 && (
              <p className="small muted" style={{ marginTop: 12 }}>
                Наблюдений по первой задаче: <span className="num">{observations.data.total}</span>.{' '}
                <Link className="link" to={`/app/observations?job_id=${routeJobIds[0]}`}>открыть</Link>
              </p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}