import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useAsset, useAssetDefects, useAssetHistory, useAssetObservations, useMapAssets, usePatchAsset } from '../data/hooks';
import {
  Badge,
  Button,
  Dialog,
  EmptyState,
  ErrorState,
  Field,
  KeyValue,
  LoadingState,
  Pagination,
  Severity,
  Status,
  Tabs,
  toast,
} from '../components/ui';
import NetworkMap from '../components/map/NetworkMap';
import { assetTypeIcon, IconChevronLeft } from '../components/icons';
import { bandTone, conditionTone, defectStatusTone, geoTone, label, lifecycleOptions, reviewStatusTone } from '../lib/labels';
import { fmtCoord, fmtDateTime, fmtNumber, fmtPercent, fmtRelative } from '../lib/format';
import { errorMessage } from '../api/client';
import { usePermissions } from '../lib/permissions';
import type { Asset } from '../api/types';

export default function AssetPassportPage() {
  const { id } = useParams<{ id: string }>();
  const { canMutate } = usePermissions();
  const asset = useAsset(id);
  const [tab, setTab] = useState('observations');
  const [editOpen, setEditOpen] = useState(false);

  if (asset.isPending) return <LoadingState label="Загрузка паспорта объекта…" />;
  if (asset.error) return <ErrorState error={asset.error} onRetry={() => asset.refetch()} />;
  const a = asset.data!;
  const Icon = assetTypeIcon(a.asset_type);

  return (
    <div>
      <div className="page-head">
        <div>
          <Link className="link small" to="/app/assets">
            <IconChevronLeft className="icon-sm" style={{ display: 'inline', verticalAlign: '-2px' }} /> Реестр объектов
          </Link>
          <div className="passport-title" style={{ marginTop: 8 }}>
            <Icon />
            <h1>{a.display_name ?? a.external_id ?? 'Объект'}</h1>
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 10 }}>
            <Badge>{label.assetType(a.asset_type)}</Badge>
            <Status tone={bandTone[a.priority_band ?? ''] ?? 'neutral'}>{label.priorityBand(a.priority_band)}</Status>
            <Badge>{label.lifecycle(a.lifecycle_status)}</Badge>
            <Status tone={geoTone[a.geolocation_status] ?? 'neutral'} shape="square">{label.geoStatus(a.geolocation_status)}</Status>
          </div>
        </div>
        <div className="page-head-actions">
          {canMutate && (
            <Button onClick={() => setEditOpen(true)}>Редактировать</Button>
          )}
          <Link className="btn" to={`/app/observations?asset_id=${a.id}`}>
            Все наблюдения
          </Link>
        </div>
      </div>

      <div className="detail-grid">
        <section className="panel" aria-label="Паспорт">
          <div className="panel-head">
            <h2 className="panel-title">Паспорт</h2>
            <span className="mono faint small">v{a.version}</span>
          </div>
          <div className="panel-body">
            <KeyValue
              items={[
                ['Идентификатор', <span className="mono small">{a.id}</span>],
                ['External ID', <span className="mono small">{a.external_id ?? '—'}</span>],
                ['Текущее состояние', <Status tone={conditionTone(a.current_condition)}>{label.condition(a.current_condition)}</Status>],
                ['Тяжесть', <Severity value={a.current_severity} />],
                ['Приоритет', <span className="num">{fmtNumber(a.current_priority, 1)} / 100</span>],
                ['Координаты', <span className="mono small">{fmtCoord(a.longitude, a.latitude)}</span>],
                ['Точность', a.location_accuracy_m != null ? <span className="num">{fmtNumber(a.location_accuracy_m, 1)} м</span> : '—'],
                ['Первое наблюдение', fmtDateTime(a.first_observed_at)],
                ['Последний осмотр', fmtDateTime(a.last_observed_at)],
                ['Обновлено', fmtDateTime(a.updated_at)],
              ]}
            />
            <hr className="divider" />
            <p className="eyebrow" style={{ marginBottom: 10 }}>Факторы приоритета · policy v{a.priority_policy_version}</p>
            <PriorityFactors asset={a} />
            {a.priority_override != null && (
              <p className="small" style={{ marginTop: 12, color: 'var(--warn)' }}>
                Ручной приоритет: {fmtNumber(a.priority_override, 0)}. Причина: {a.priority_override_reason ?? '—'}
              </p>
            )}
          </div>
        </section>

        <section className="panel" aria-label="Положение на карте">
          <div className="panel-head">
            <h2 className="panel-title">Положение</h2>
            <Link className="link small" to={`/app/map?selected=${a.id}&layer=assets`}>на карте</Link>
          </div>
          <div className="detail-map">
            {a.longitude != null && a.latitude != null ? (
              <AssetMiniMap asset={a} />
            ) : (
              <EmptyState title="Координаты недоступны">
                Объект создан без GPS (статус UNAVAILABLE). Положение можно задать вручную через редактирование.
              </EmptyState>
            )}
          </div>
        </section>
      </div>

      <div className="panel" style={{ marginTop: 'var(--sp-5)' }}>
        <Tabs
          tabs={[
            { id: 'observations', label: 'Наблюдения' },
            { id: 'defects', label: 'Дефекты' },
            { id: 'history', label: 'История состояния' },
          ]}
          active={tab}
          onChange={setTab}
        />
        {tab === 'observations' && <AssetObservations id={a.id} />}
        {tab === 'defects' && <AssetDefects id={a.id} />}
        {tab === 'history' && <AssetHistory id={a.id} />}
      </div>

      {editOpen && <EditAssetDialog asset={a} onClose={() => setEditOpen(false)} />}
    </div>
  );
}

function PriorityFactors({ asset }: { asset: Asset }) {
  const f = asset.priority_factors ?? {};
  const items: [string, string][] = [
    ['Тяжесть', f.severity != null ? `${f.severity}/5` : '—'],
    ['Уверенность ML', f.confidence != null ? fmtPercent(Number(f.confidence), 0) : '—'],
    ['Impact-фактор', f.impact_factor != null ? fmtNumber(Number(f.impact_factor), 2) : '—'],
    ['Расчётный приоритет', f.computed_priority != null ? fmtNumber(Number(f.computed_priority), 1) : '—'],
    ['Решение review', f.review_decision ? label.reviewStatus(String(f.review_decision)) : '—'],
    ['Дедупликация', f.deduplication_result ? label.dedup(String(f.deduplication_result)) : '—'],
  ];
  return (
    <div className="factor-grid">
      {items.map(([k, v]) => (
        <div className="factor" key={k}>
          <div className="factor-label">{k}</div>
          <div className="factor-value">{v}</div>
        </div>
      ))}
    </div>
  );
}

function AssetMiniMap({ asset }: { asset: Asset }) {
  const map = useMapAssets({ limit: 500 });
  return (
    <NetworkMap
      assets={map.data ?? null}
      visible={{ assets: true, defects: false, observations: false, routes: false }}
      selectedId={asset.id}
    />
  );
}

function AssetObservations({ id }: { id: string }) {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const q = useAssetObservations(id, { page, page_size: 10 });
  if (q.isPending) return <LoadingState />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const data = q.data!;
  if (data.items.length === 0) return <EmptyState title="Наблюдений пока нет" />;
  return (
    <>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Время</th>
              <th>Состояние (ML)</th>
              <th>Эффективное</th>
              <th>Уверенность</th>
              <th>Дедупликация</th>
              <th>Проверка</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((o) => (
              <tr key={o.id} className="clickable" onClick={() => navigate(`/app/observations/${o.id}`)}>
                <td className="muted">{fmtDateTime(o.observed_at)}</td>
                <td>{label.condition(o.condition_class)} <Severity value={o.severity} /></td>
                <td>{label.condition(o.effective_condition ?? o.condition_class)}</td>
                <td className="num">{fmtPercent(o.detector_confidence, 0)}</td>
                <td><Status tone={o.dedup_result === 'MATCHED' ? 'ok' : o.dedup_result === 'NEW_ASSET' ? 'accent' : 'warn'} shape="square">{label.dedup(o.dedup_result)}</Status></td>
                <td><Status tone={reviewStatusTone[o.review_status] ?? 'neutral'}>{label.reviewStatus(o.review_status)}</Status></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pagination page={data.page} pages={data.pages} total={data.total} pageSize={data.page_size} onPage={setPage} noun={['наблюдение', 'наблюдения', 'наблюдений']} />
    </>
  );
}

function AssetDefects({ id }: { id: string }) {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const q = useAssetDefects(id, { page, page_size: 10 });
  if (q.isPending) return <LoadingState />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const data = q.data!;
  if (data.items.length === 0) return <EmptyState title="Дефекты не зарегистрированы" />;
  return (
    <>
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              <th>Дефект</th>
              <th>Статус</th>
              <th>Тяжесть</th>
              <th>Наблюдений</th>
              <th>Последнее</th>
            </tr>
          </thead>
          <tbody>
            {data.items.map((d) => (
              <tr key={d.id} className="clickable" onClick={() => navigate(`/app/defects/${d.id}`)}>
                <td className="cell-main">{label.defectType(d.defect_type)}</td>
                <td><Status tone={defectStatusTone[d.status] ?? 'neutral'}>{label.defectStatus(d.status)}</Status></td>
                <td><Severity value={d.severity} /></td>
                <td className="num">{d.observation_count ?? '—'}</td>
                <td className="muted">{fmtRelative(d.last_detected_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Pagination page={data.page} pages={data.pages} total={data.total} pageSize={data.page_size} onPage={setPage} noun={['дефект', 'дефекта', 'дефектов']} />
    </>
  );
}

function AssetHistory({ id }: { id: string }) {
  const q = useAssetHistory(id);
  if (q.isPending) return <LoadingState />;
  if (q.error) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;
  const items = q.data!.items;
  if (items.length === 0) return <EmptyState title="История пуста" />;
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            <th>Когда</th>
            <th>Состояние (было → стало)</th>
            <th>Тяжесть</th>
            <th>Источник</th>
            <th>Физическое изменение</th>
            <th>Примечание</th>
          </tr>
        </thead>
        <tbody>
          {items.map((h) => (
            <tr key={h.id}>
              <td className="muted">{fmtDateTime(h.detected_at)}</td>
              <td>
                <span className="small">
                  {h.previous_condition ? <span className="faint">{label.condition(h.previous_condition)} → </span> : null}
                  <Status tone={conditionTone(h.new_condition)}>{label.condition(h.new_condition)}</Status>
                </span>
              </td>
              <td><Severity value={h.new_severity} /></td>
              <td>{label.changeSource(h.change_source)}</td>
              <td>{h.is_physical_change ? <Status tone="warn" shape="diamond">да</Status> : <span className="faint">нет</span>}</td>
              <td className="muted small">{h.note ?? '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function EditAssetDialog({ asset, onClose }: { asset: Asset; onClose: () => void }) {
  const patch = usePatchAsset();
  const [name, setName] = useState(asset.display_name ?? '');
  const [externalId, setExternalId] = useState(asset.external_id ?? '');
  const [lifecycle, setLifecycle] = useState(asset.lifecycle_status);
  const [override, setOverride] = useState(asset.priority_override != null ? String(asset.priority_override) : '');
  const [overrideReason, setOverrideReason] = useState(asset.priority_override_reason ?? '');
  const [lon, setLon] = useState(asset.longitude != null ? String(asset.longitude) : '');
  const [lat, setLat] = useState(asset.latitude != null ? String(asset.latitude) : '');
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    const body: Record<string, unknown> = { expected_version: asset.version };
    if (name !== (asset.display_name ?? '')) body.display_name = name;
    if (externalId !== (asset.external_id ?? '')) body.external_id = externalId;
    if (lifecycle !== asset.lifecycle_status) body.lifecycle_status = lifecycle;
    if (override !== '') {
      const v = Number(override);
      if (Number.isNaN(v) || v < 0 || v > 100) {
        setError('Приоритет должен быть числом 0–100.');
        return;
      }
      if (!overrideReason.trim()) {
        setError('Для ручного приоритета обязательна причина.');
        return;
      }
      body.priority_override = v;
      body.priority_override_reason = overrideReason.trim();
    }
    if (lon !== '' && lat !== '') {
      const lo = Number(lon);
      const la = Number(lat);
      if (Number.isNaN(lo) || Number.isNaN(la) || lo < -180 || lo > 180 || la < -90 || la > 90) {
        setError('Координаты: lon ∈ [−180, 180], lat ∈ [−90, 90].');
        return;
      }
      body.location = { longitude: lo, latitude: la };
    }
    try {
      await patch.mutateAsync({ id: asset.id, patch: body as never });
      toast('success', 'Паспорт объекта обновлён.');
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  return (
    <Dialog
      open
      onClose={onClose}
      title="Редактирование объекта"
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Отмена</Button>
          <Button variant="primary" loading={patch.isPending} onClick={() => void submit()}>Сохранить</Button>
        </>
      }
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' }}>
        {error && <div className="login-error" role="alert">{error}</div>}
        <p className="faint small">
          Оптимистичная блокировка: версия {asset.version}. Если объект изменил другой оператор, сервер вернёт конфликт.
        </p>
        <Field label="Название">
          <input className="input" value={name} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="External ID">
          <input className="input" value={externalId} onChange={(e) => setExternalId(e.target.value)} />
        </Field>
        <Field label="Жизненный цикл">
          <select className="select" value={lifecycle} onChange={(e) => setLifecycle(e.target.value as Asset['lifecycle_status'])}>
            {lifecycleOptions.map((l) => <option key={l.value} value={l.value}>{l.name}</option>)}
          </select>
        </Field>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--sp-3)' }}>
          <Field label="Долгота (lon)">
            <input className="input mono" value={lon} onChange={(e) => setLon(e.target.value)} placeholder="37.6173" />
          </Field>
          <Field label="Широта (lat)">
            <input className="input mono" value={lat} onChange={(e) => setLat(e.target.value)} placeholder="55.7558" />
          </Field>
        </div>
        <Field label="Ручной приоритет (0–100)" hint="Пусто — без переопределения">
          <input className="input mono" value={override} onChange={(e) => setOverride(e.target.value)} />
        </Field>
        {override !== '' && (
          <Field label="Причина переопределения" error={!overrideReason.trim() ? 'Обязательно при ручном приоритете' : undefined}>
            <textarea className="textarea" value={overrideReason} onChange={(e) => setOverrideReason(e.target.value)} />
          </Field>
        )}
      </div>
    </Dialog>
  );
}