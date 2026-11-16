/* Контекстные панели инспекции: Asset / Observation / Defect / Route.
   Confidence модели, severity дефекта и priority задачи — раздельные величины.
   Отсутствующие значения показываются как «—», не маскируются. */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import {
  useAsset,
  useAssetDefects,
  useAssetHistory,
  useAssetObservations,
  useCreateReview,
  useDefect,
  useObservation,
  useRoute,
} from '../../data/hooks';
import { usePermissions } from '../../lib/permissions';
import type { Asset, ConditionHistory, Defect, Observation } from '../../api/types';
import { assetTypeIcon } from '../icons';
import { Badge, Button, EmptyState, ErrorState, KeyValue, LoadingState, Severity, Status, Tabs, toast } from '../ui';
import {
  bandTone,
  conditionTone,
  defectStatusTone,
  geoTone,
  label,
  reviewStatusTone,
} from '../../lib/labels';
import { fmtCoord, fmtDateTime, fmtNumber, fmtPercent, fmtRelative } from '../../lib/format';

export type InspectionTab = 'overview' | 'observations' | 'defects' | 'history' | 'compare';

export interface SelectionNav {
  layer: 'assets' | 'defects' | 'observations' | 'routes';
  id: string;
}

/* ── Asset ─────────────────────────────────────────── */
export function AssetInspection({
  assetId,
  tab,
  onTab,
  onNavigate,
}: {
  assetId: string;
  tab: InspectionTab;
  onTab: (t: InspectionTab) => void;
  onNavigate: (sel: SelectionNav) => void;
}) {
  const asset = useAsset(assetId);
  const observations = useAssetObservations(assetId, { page_size: 20 });
  const defects = useAssetDefects(assetId, { page_size: 20 });
  const history = useAssetHistory(assetId);

  if (asset.isPending) return <LoadingState />;
  if (asset.error) return <ErrorState error={asset.error} onRetry={() => void asset.refetch()} />;
  if (!asset.data) return <EmptyState title="Объект не найден" />;
  const a = asset.data;
  const Icon = assetTypeIcon(a.asset_type);
  const obsItems = observations.data?.items ?? [];
  const defectItems = defects.data?.items ?? [];
  const historyItems = history.data?.items ?? [];

  return (
    <div>
      <div className="passport-title" style={{ marginBottom: 12 }}>
        <Icon />
        <h2 className="panel-title">{a.display_name ?? a.external_id ?? 'Объект'}</h2>
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
        <Status tone={bandTone[a.priority_band ?? ''] ?? 'neutral'}>{label.priorityBand(a.priority_band)}</Status>
        <Badge>{label.assetType(a.asset_type)}</Badge>
        {a.external_id && <Badge>{a.external_id}</Badge>}
      </div>
      <Tabs
        tabs={[
          { id: 'overview', label: 'Обзор' },
          { id: 'observations', label: 'Наблюдения', count: observations.data?.total },
          { id: 'defects', label: 'Дефекты', count: defects.data?.total },
          { id: 'history', label: 'История', count: history.data?.total },
          { id: 'compare', label: 'Сравнение' },
        ]}
        active={tab}
        onChange={(t) => onTab(t as InspectionTab)}
      />
      <div style={{ marginTop: 12 }}>
        {tab === 'overview' && <AssetOverview asset={a} />}
        {tab === 'observations' && (
          <ObservationList items={obsItems} pending={observations.isPending} onNavigate={onNavigate} />
        )}
        {tab === 'defects' && (
          <DefectList items={defectItems} pending={defects.isPending} onNavigate={onNavigate} />
        )}
        {tab === 'history' && <HistoryTimeline items={historyItems} pending={history.isPending} />}
        {tab === 'compare' && <ObservationCompare items={obsItems} history={historyItems} />}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 16 }}>
        <Link className="btn btn-primary btn-block" to={`/app/assets/${a.id}`}>
          Паспорт объекта
        </Link>
        <Link className="btn btn-block" to={`/app/observations?asset_id=${a.id}`}>
          Все наблюдения объекта
        </Link>
      </div>
    </div>
  );
}

function AssetOverview({ asset: a }: { asset: Asset }) {
  const accuracy = a.location_accuracy_m;
  return (
    <>
      <KeyValue
        items={[
          ['Состояние', <Status tone={conditionTone(a.current_condition)}>{label.condition(a.current_condition)}</Status>],
          ['Тяжесть (состояние)', <Severity value={a.current_severity} />],
          ['Приоритет задачи', <span className="num">{fmtNumber(a.current_priority, 1)} / 100</span>],
          ['Геолокация', <Status tone={geoTone[a.geolocation_status] ?? 'neutral'} shape="square">{label.geoStatus(a.geolocation_status)}</Status>],
          ['Координаты', <span className="mono small">{fmtCoord(a.longitude, a.latitude)}</span>],
          ['Точность GPS', accuracy != null ? <span className="num">±{fmtNumber(accuracy, 1)} м</span> : <span className="muted">—</span>],
          ['Последний осмотр', fmtRelative(a.last_observed_at)],
          ['Первый осмотр', fmtRelative(a.first_observed_at)],
          ['Версия записи', <span className="num">{a.version}</span>],
        ]}
      />
      {a.geolocation_status === 'ESTIMATED' && (
        <p className="faint" style={{ fontSize: 'var(--text-micro)', marginTop: 8 }}>
          Положение оценочное (интерполяция GPS-трека). Кольцо неопределённости на карте
          соответствует точности ±{fmtNumber(accuracy, 1)} м.
        </p>
      )}
      {a.geolocation_status === 'UNAVAILABLE' && (
        <p className="faint" style={{ fontSize: 'var(--text-micro)', marginTop: 8 }}>
          Координаты недоступны — объект не отображается на карте. Положение можно задать
          вручную в паспорте.
        </p>
      )}
    </>
  );
}

function ObservationList({
  items,
  pending,
  onNavigate,
}: {
  items: Observation[];
  pending: boolean;
  onNavigate: (sel: SelectionNav) => void;
}) {
  if (pending) return <LoadingState />;
  if (items.length === 0) return <EmptyState title="Наблюдений пока нет" />;
  return (
    <div className="inspection-list">
      {items.map((o) => (
        <button key={o.id} className="inspection-row" onClick={() => onNavigate({ layer: 'observations', id: o.id })}>
          {o.image_url ? (
            <img className="inspection-thumb" src={o.image_url} alt="" loading="lazy" />
          ) : (
            <span className="inspection-thumb inspection-thumb-empty" aria-hidden>—</span>
          )}
          <span className="inspection-row-body">
            <span className="inspection-row-title">
              <Status tone={conditionTone(o.condition_class)}>{label.condition(o.condition_class)}</Status>
              <Status tone={reviewStatusTone[o.review_status] ?? 'neutral'}>{label.reviewStatus(o.review_status)}</Status>
            </span>
            <span className="faint small">
              {fmtDateTime(o.observed_at)} · confidence {fmtPercent(o.detector_confidence)}
            </span>
          </span>
        </button>
      ))}
    </div>
  );
}

function DefectList({
  items,
  pending,
  onNavigate,
}: {
  items: Defect[];
  pending: boolean;
  onNavigate: (sel: SelectionNav) => void;
}) {
  if (pending) return <LoadingState />;
  if (items.length === 0) return <EmptyState title="Дефектов не зарегистрировано" />;
  return (
    <div className="inspection-list">
      {items.map((d) => (
        <button key={d.id} className="inspection-row" onClick={() => onNavigate({ layer: 'defects', id: d.id })}>
          <span className="inspection-row-body">
            <span className="inspection-row-title">
              {label.defectType(d.defect_type)}
              <Severity value={d.severity} />
              <Status tone={defectStatusTone[d.status] ?? 'neutral'}>{label.defectStatus(d.status)}</Status>
            </span>
            <span className="faint small">
              {fmtDateTime(d.first_detected_at)} → {fmtRelative(d.last_detected_at)}
              {d.observation_count != null && ` · наблюдений: ${d.observation_count}`}
            </span>
          </span>
        </button>
      ))}
    </div>
  );
}

function HistoryTimeline({ items, pending }: { items: ConditionHistory[]; pending: boolean }) {
  if (pending) return <LoadingState />;
  if (items.length === 0) return <EmptyState title="История изменений пуста" />;
  return (
    <ol className="history-timeline">
      {items.map((h) => (
        <li key={h.id} className={h.is_physical_change ? 'history-item history-physical' : 'history-item'}>
          <div className="history-item-head">
            <span className="small">{fmtDateTime(h.detected_at)}</span>
            <Badge>{label.changeSource(h.change_source)}</Badge>
            {h.is_physical_change && <Badge tone="crit">Физическое изменение</Badge>}
          </div>
          <div className="small">
            {label.condition(h.previous_condition)} → <strong>{label.condition(h.new_condition)}</strong>
            {h.previous_severity != null && h.new_severity != null && (
              <span className="faint"> · S{h.previous_severity} → S{h.new_severity}</span>
            )}
          </div>
          {h.note && <p className="faint" style={{ fontSize: 'var(--text-micro)' }}>{h.note}</p>}
        </li>
      ))}
    </ol>
  );
}

function ObservationCompare({ items, history }: { items: Observation[]; history: ConditionHistory[] }) {
  const sorted = [...items].sort((a, b) => (b.observed_at ?? '').localeCompare(a.observed_at ?? ''));
  const current = sorted[0];
  const previous = sorted[1];
  if (!current || !previous) {
    return <EmptyState title="Недостаточно наблюдений">Для сравнения нужны минимум два объезда этого объекта.</EmptyState>;
  }
  const physical = history.find((h) => h.is_physical_change);
  return (
    <div>
      {physical && (
        <div className="compare-alert" role="note">
          <Badge tone="crit">Физическое изменение</Badge>
          <span className="small">
            {label.condition(physical.previous_condition)} → {label.condition(physical.new_condition)}
            {' '}({fmtDateTime(physical.detected_at)})
          </span>
        </div>
      )}
      <div className="compare-grid">
        {[previous, current].map((o, i) => (
          <figure key={o.id} className="compare-card">
            <figcaption className="eyebrow">{i === 0 ? 'Предыдущее' : 'Текущее'} · {fmtDateTime(o.observed_at)}</figcaption>
            {o.image_url ? (
              <img src={o.image_url} alt={`Кадр наблюдения ${fmtDateTime(o.observed_at)}`} loading="lazy" />
            ) : (
              <div className="compare-noimage">Кадр недоступен</div>
            )}
            <KeyValue
              items={[
                ['Состояние', <Status tone={conditionTone(o.condition_class)}>{label.condition(o.condition_class)}</Status>],
                ['Тяжесть ML', <Severity value={o.severity} />],
                ['Confidence', <span className="num">{fmtPercent(o.detector_confidence)}</span>],
                ['Проверка', label.reviewStatus(o.review_status)],
              ]}
            />
          </figure>
        ))}
      </div>
      <p className="faint" style={{ fontSize: 'var(--text-micro)', marginTop: 8 }}>
        Сравнение исходных ML-предсказаний двух объездов. Решение оператора отображается
        отдельно и не затирает исходные данные модели.
      </p>
    </div>
  );
}

/* ── Observation ───────────────────────────────────── */
export function ObservationInspection({
  observationId,
  onNavigate,
  onConfirmed,
}: {
  observationId: string;
  onNavigate: (sel: SelectionNav) => void;
  onConfirmed?: () => void;
}) {
  const observation = useObservation(observationId);
  const { canMutate, isDemo } = usePermissions();
  const createReview = useCreateReview();
  const [comment, setComment] = useState('');

  if (observation.isPending) return <LoadingState />;
  if (observation.error) return <ErrorState error={observation.error} onRetry={() => void observation.refetch()} />;
  if (!observation.data) return <EmptyState title="Наблюдение не найдено" />;
  const o = observation.data;

  const confirm = () => {
    createReview.mutate(
      { observation_id: o.id, decision: 'CONFIRMED', comment: comment || (isDemo ? 'Подтверждено в демо-сценарии.' : null) },
      {
        onSuccess: () => {
          toast('success', 'Наблюдение подтверждено');
          onConfirmed?.();
        },
        onError: (e) => toast('error', `Не удалось подтвердить: ${e instanceof Error ? e.message : 'ошибка'}`),
      },
    );
  };

  return (
    <div>
      <p className="eyebrow" style={{ marginBottom: 8 }}>Наблюдение · {fmtDateTime(o.observed_at)}</p>
      {o.image_url ? (
        <img className="inspection-image" src={o.image_url} alt="Кадр наблюдения" />
      ) : (
        <div className="compare-noimage" style={{ marginBottom: 12 }}>
          Кадр недоступен{!canMutate ? ' (нет прав на медиа)' : ''}
        </div>
      )}
      <KeyValue
        items={[
          ['Тип (ML)', label.assetType(o.object_type)],
          ['Состояние (ML)', <Status tone={conditionTone(o.condition_class)}>{label.condition(o.condition_class)}</Status>],
          ['Confidence модели', <span className="num">{fmtPercent(o.detector_confidence)}</span>],
          ['Тяжесть (ML)', <Severity value={o.severity} />],
          ['Проверка оператором', <Status tone={reviewStatusTone[o.review_status] ?? 'neutral'}>{label.reviewStatus(o.review_status)}</Status>],
          ['Эффективное состояние', o.effective_condition ? label.condition(o.effective_condition) : <span className="muted">—</span>],
          ['Дедупликация', o.dedup_result ? `${label.dedup(o.dedup_result)}${o.dedup_score != null ? ` · ${fmtPercent(o.dedup_score)}` : ''}` : <span className="muted">—</span>],
          ['Координаты', <span className="mono small">{fmtCoord(o.longitude, o.latitude)}</span>],
          ['Точность GPS', o.location_accuracy_m != null ? <span className="num">±{fmtNumber(o.location_accuracy_m, 1)} м</span> : <span className="muted">—</span>],
          ['Геолокация', <Status tone={geoTone[o.geolocation_status] ?? 'neutral'} shape="square">{label.geoStatus(o.geolocation_status)}</Status>],
          ['Источник координат', o.geolocation_source],
          ['Время инференса', fmtDateTime(o.detected_at)],
        ]}
      />
      {o.asset_id && (
        <Button size="sm" block style={{ marginTop: 12 }} onClick={() => onNavigate({ layer: 'assets', id: o.asset_id! })}>
          Показать объект на карте
        </Button>
      )}
      {o.review_status === 'UNREVIEWED' && canMutate && (
        <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
          <input
            className="input"
            placeholder="Комментарий (необязательно)"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            aria-label="Комментарий к подтверждению"
          />
          <Button variant="primary" block loading={createReview.isPending} onClick={confirm}>
            Подтвердить наблюдение{isDemo ? ' (DEMO)' : ''}
          </Button>
        </div>
      )}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 12 }}>
        <Link className="btn btn-block" to={`/app/observations/${o.id}`}>
          Карточка наблюдения
        </Link>
        {o.asset_id && (
          <Link className="btn btn-block" to={`/app/assets/${o.asset_id}`}>
            Паспорт объекта
          </Link>
        )}
      </div>
    </div>
  );
}

/* ── Defect ────────────────────────────────────────── */
export function DefectInspection({
  defectId,
  onNavigate,
}: {
  defectId: string;
  onNavigate: (sel: SelectionNav) => void;
}) {
  const defect = useDefect(defectId);
  const asset = useAsset(defect.data?.asset_id);

  if (defect.isPending) return <LoadingState />;
  if (defect.error) return <ErrorState error={defect.error} onRetry={() => void defect.refetch()} />;
  if (!defect.data) return <EmptyState title="Дефект не найден" />;
  const d = defect.data;

  return (
    <div>
      <p className="eyebrow" style={{ marginBottom: 8 }}>Дефект</p>
      <h2 className="panel-title" style={{ marginBottom: 12 }}>{label.defectType(d.defect_type)}</h2>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 12 }}>
        <Severity value={d.severity} />
        <Status tone={defectStatusTone[d.status] ?? 'neutral'}>{label.defectStatus(d.status)}</Status>
      </div>
      <KeyValue
        items={[
          ['Объект', asset.data ? (asset.data.display_name ?? asset.data.external_id ?? 'Объект') : <span className="muted">…</span>],
          ['Приоритет объекта', asset.data?.current_priority != null ? <span className="num">{fmtNumber(asset.data.current_priority, 1)} / 100</span> : <span className="muted">—</span>],
          ['Впервые обнаружен', fmtDateTime(d.first_detected_at)],
          ['Последнее обнаружение', fmtDateTime(d.last_detected_at)],
          ['Устранён', d.resolved_at ? fmtDateTime(d.resolved_at) : <span className="muted">—</span>],
          ['Наблюдений', d.observation_count != null ? <span className="num">{d.observation_count}</span> : <span className="muted">—</span>],
        ]}
      />
      {d.description && <p className="small muted" style={{ marginTop: 8 }}>{d.description}</p>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 16 }}>
        <Button variant="primary" block onClick={() => onNavigate({ layer: 'assets', id: d.asset_id })}>
          Показать объект на карте
        </Button>
        <Link className="btn btn-block" to={`/app/defects/${d.id}`}>
          Карточка дефекта
        </Link>
      </div>
    </div>
  );
}

/* ── Route ─────────────────────────────────────────── */
export function RouteInspection({ routeId }: { routeId: string }) {
  const route = useRoute(routeId);
  if (route.isPending) return <LoadingState />;
  if (route.error) return <ErrorState error={route.error} onRetry={() => void route.refetch()} />;
  if (!route.data) return <EmptyState title="Маршрут не найден" />;
  const r = route.data;
  const points = (r.track_geojson?.coordinates as [number, number][] | undefined)?.length ?? 0;
  return (
    <div>
      <p className="eyebrow" style={{ marginBottom: 8 }}>Маршрут</p>
      <h2 className="panel-title" style={{ marginBottom: 12 }}>{r.name}</h2>
      <KeyValue
        items={[
          ['Транспорт', r.vehicle_id ?? <span className="muted">—</span>],
          ['Начало', fmtDateTime(r.started_at)],
          ['Окончание', fmtDateTime(r.finished_at)],
          ['Дистанция', r.total_distance_m != null ? <span className="num">{fmtNumber(r.total_distance_m)} м</span> : <span className="muted">—</span>],
          ['Точек трека', <span className="num">{points}</span>],
        ]}
      />
      <Link className="btn btn-primary btn-block" style={{ marginTop: 16 }} to={`/app/routes/${r.id}`}>
        Карточка маршрута
      </Link>
    </div>
  );
}
