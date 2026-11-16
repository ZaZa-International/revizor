import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCreateRoute, useRoutes } from '../data/hooks';
import { Button, Dialog, EmptyState, ErrorState, Field, LoadingState, Pagination, toast } from '../components/ui';
import { IconPlus, IconRoute } from '../components/icons';
import { fmtDateTime, fmtDistance } from '../lib/format';
import { errorMessage } from '../api/client';
import { usePermissions } from '../lib/permissions';

export default function RoutesPage() {
  const navigate = useNavigate();
  const { canMutate } = usePermissions();
  const [page, setPage] = useState(1);
  const routes = useRoutes({ page, page_size: 20 });
  const [createOpen, setCreateOpen] = useState(false);

  return (
    <div>
      <div className="page-head">
        <div>
          <p className="eyebrow">Обследования</p>
          <h1>Маршруты</h1>
          <p className="page-desc">
            Треки объездов служебных автомобилей. Маршрут связывает загрузки, задачи и наблюдения в единую последовательность обследования.
          </p>
        </div>
        <div className="page-head-actions">
          {canMutate && (
            <Button variant="primary" onClick={() => setCreateOpen(true)}>
              <IconPlus className="icon-sm" /> Новый маршрут
            </Button>
          )}
        </div>
      </div>

      <div className="panel">
        {routes.isPending && <LoadingState />}
        {routes.error && <ErrorState error={routes.error} onRetry={() => routes.refetch()} />}
        {routes.data && routes.data.items.length === 0 && (
          <EmptyState title="Маршрутов пока нет">
            Создайте маршрут с треком (≥2 точек) или загрузите материалы с GPS-треком в metadata.
          </EmptyState>
        )}
        {routes.data && routes.data.items.length > 0 && (
          <>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Маршрут</th>
                    <th>Автомобиль</th>
                    <th>Дистанция</th>
                    <th>Начало</th>
                    <th>Завершение</th>
                  </tr>
                </thead>
                <tbody>
                  {routes.data.items.map((r) => (
                    <tr key={r.id} className="clickable" tabIndex={0}
                      onClick={() => navigate(`/app/routes/${r.id}`)}
                      onKeyDown={(e) => { if (e.key === 'Enter') navigate(`/app/routes/${r.id}`); }}
                    >
                      <td>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                          <IconRoute style={{ color: 'var(--accent-dim)' }} />
                          <span className="cell-main">{r.name}</span>
                        </span>
                      </td>
                      <td className="mono small">{r.vehicle_id ?? '—'}</td>
                      <td className="num">{fmtDistance(r.total_distance_m)}</td>
                      <td className="muted">{fmtDateTime(r.started_at)}</td>
                      <td className="muted">{fmtDateTime(r.finished_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={routes.data.page} pages={routes.data.pages} total={routes.data.total} pageSize={routes.data.page_size}
              onPage={setPage} noun={['маршрут', 'маршрута', 'маршрутов']} />
          </>
        )}
      </div>

      {createOpen && <CreateRouteDialog onClose={() => setCreateOpen(false)} />}
    </div>
  );
}

function CreateRouteDialog({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const create = useCreateRoute();
  const [name, setName] = useState('');
  const [vehicle, setVehicle] = useState('');
  const [trackText, setTrackText] = useState('');
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    if (!name.trim()) {
      setError('Укажите название маршрута.');
      return;
    }
    let track: [number, number][];
    try {
      const parsed = JSON.parse(trackText);
      if (!Array.isArray(parsed) || parsed.length < 2) throw new Error();
      track = parsed.map((p: unknown) => {
        if (!Array.isArray(p) || p.length !== 2 || p.some((v) => typeof v !== 'number')) throw new Error();
        return [p[0], p[1]] as [number, number];
      });
      if (track.some(([lon, lat]) => lon < -180 || lon > 180 || lat < -90 || lat > 90)) {
        setError('Координаты вне диапазона: lon ∈ [−180,180], lat ∈ [−90,90].');
        return;
      }
    } catch {
      setError('Трек: JSON-массив пар [lon, lat], минимум 2 точки. Пример: [[37.61,55.75],[37.62,55.76]]');
      return;
    }
    try {
      const route = await create.mutateAsync({
        name: name.trim(),
        vehicle_id: vehicle.trim() || undefined,
        track,
      });
      toast('success', 'Маршрут создан. Дистанция рассчитана PostGIS.');
      onClose();
      navigate(`/app/routes/${route.id}`);
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  return (
    <Dialog
      open
      onClose={onClose}
      title="Новый маршрут"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Отмена</Button>
          <Button variant="primary" loading={create.isPending} onClick={() => void submit()}>Создать</Button>
        </>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' }}>
        {error && <div className="login-error" role="alert">{error}</div>}
        <Field label="Название">
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} placeholder="Объезд №12 — Тверской район" />
        </Field>
        <Field label="Автомобиль (необязательно)">
          <input className="input" value={vehicle} onChange={(e) => setVehicle(e.target.value)} placeholder="МГТС-001" />
        </Field>
        <Field label="Трек [lon, lat]" hint="JSON-массив пар координат, ≥2 точек. Порядок: долгота, широта.">
          <textarea
            className="textarea mono"
            value={trackText}
            onChange={(e) => setTrackText(e.target.value)}
            placeholder='[[37.6100, 55.7550], [37.6150, 55.7565], [37.6250, 55.7580]]'
            style={{ minHeight: 110 }}
          />
        </Field>
      </div>
    </Dialog>
  );
}