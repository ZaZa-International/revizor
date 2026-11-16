import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { useCreateReview, useObservation, useObservations, useReviews } from '../data/hooks';
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Field,
  KeyValue,
  LoadingState,
  Severity,
  Status,
  toast,
} from '../components/ui';
import { assetTypeIcon, IconCheck, IconClose, IconAlert } from '../components/icons';
import { assetTypeOptions, conditionOptions, dedupTone, label } from '../lib/labels';
import { fmtDateTime, fmtPercent, fmtRelative } from '../lib/format';
import { bboxStyle } from '../lib/bbox';
import { errorMessage } from '../api/client';
import { usePermissions } from '../lib/permissions';
import type { ReviewCreate } from '../api/types';

type Decision = 'CONFIRMED' | 'REJECTED' | 'CORRECTED' | 'NEEDS_MORE_INFORMATION';

const DECISIONS: { id: Decision; name: string; hint: string; cls: string; key: string }[] = [
  { id: 'CONFIRMED', name: 'Подтвердить', hint: 'Предсказание верно', cls: 'confirm', key: '1' },
  { id: 'REJECTED', name: 'Отклонить', hint: 'Ложное обнаружение', cls: 'reject', key: '2' },
  { id: 'CORRECTED', name: 'Скорректировать', hint: 'Тип / состояние / тяжесть', cls: 'correct', key: '3' },
  { id: 'NEEDS_MORE_INFORMATION', name: 'Нужны данные', hint: 'Недостаточно контекста', cls: '', key: '4' },
];

export default function ReviewsPage() {
  const { canMutate } = usePermissions();
  const [params, setParams] = useSearchParams();
  const queue = useObservations({ review_status: 'UNREVIEWED', page_size: 50 });
  const items = useMemo(() => queue.data?.items ?? [], [queue.data]);
  const selectedId = params.get('obs') ?? items[0]?.id ?? null;
  const selected = useObservation(selectedId ?? undefined);
  const [imgFailed, setImgFailed] = useState(false);

  useEffect(() => setImgFailed(false), [selectedId]);

  const select = (id: string) => {
    const next = new URLSearchParams(params);
    next.set('obs', id);
    setParams(next, { replace: true });
  };

  if (queue.isPending) return <LoadingState label="Загрузка очереди проверки…" />;
  if (queue.error) return <ErrorState error={queue.error} onRetry={() => queue.refetch()} />;

  return (
    <div>
      <div className="page-head">
        <div>
          <p className="eyebrow">Human-in-the-loop</p>
          <h1>Проверка оператором</h1>
          <p className="page-desc">
            Подтвердите, отклоните или скорректируйте предсказание ML. Решения сохраняются в append-only истории и применяются к объекту сервером.
          </p>
        </div>
        <div className="page-head-actions">
          <Badge tone={items.length > 0 ? 'warn' : undefined}>в очереди: {queue.data?.total ?? 0}</Badge>
        </div>
      </div>

      {items.length === 0 ? (
        <div className="panel">
          <EmptyState title="Очередь пуста">
            Все наблюдения проверены. Новые записи появятся после обработки следующих объездов.
          </EmptyState>
        </div>
      ) : (
        <div className="review-workspace">
          <section className="panel review-queue" aria-label="Очередь проверки">
            {items.map((o) => {
              const Icon = assetTypeIcon(o.object_type);
              return (
                <button key={o.id} className="review-queue-item" aria-current={o.id === selectedId} onClick={() => select(o.id)}>
                  {o.crop_url ? (
                    <img src={o.crop_url} alt="" loading="lazy" />
                  ) : (
                    <span style={{ width: 72, height: 44, display: 'grid', placeItems: 'center', background: 'var(--raised)', borderRadius: 3, flex: 'none' }}>
                      <Icon />
                    </span>
                  )}
                  <span style={{ minWidth: 0, flex: 1 }}>
                    <span className="att-title" style={{ display: 'block', fontSize: 'var(--text-small)', fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {label.assetTypeShort(o.object_type)} · {label.condition(o.condition_class)}
                    </span>
                    <span className="att-sub" style={{ display: 'block', fontSize: 'var(--text-micro)', color: 'var(--faint)', marginTop: 2 }}>
                      {fmtRelative(o.observed_at)} · {fmtPercent(o.detector_confidence, 0)}
                      {o.dedup_result === 'POSSIBLE_MATCH' || o.dedup_result === 'AMBIGUOUS' ? ' · совпадение?' : ''}
                    </span>
                  </span>
                </button>
              );
            })}
          </section>

          <div>
            {selected.isPending && <div className="panel"><LoadingState /></div>}
            {selected.error && <div className="panel"><ErrorState error={selected.error} onRetry={() => selected.refetch()} /></div>}
            {selected.data && (
              <ReviewCard
                key={selected.data.id}
                observationId={selected.data.id}
                canMutate={canMutate}
                imgFailed={imgFailed}
                onImgError={() => setImgFailed(true)}
                onDone={() => {
                  const remaining = items.filter((x) => x.id !== selected.data!.id);
                  void queue.refetch().then(() => {
                    if (remaining[0]) select(remaining[0].id);
                    else {
                      const next = new URLSearchParams(params);
                      next.delete('obs');
                      setParams(next, { replace: true });
                    }
                  });
                }}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function ReviewCard({
  observationId,
  canMutate,
  imgFailed,
  onImgError,
  onDone,
}: {
  observationId: string;
  canMutate: boolean;
  imgFailed: boolean;
  onImgError: () => void;
  onDone: () => void;
}) {
  const obs = useObservation(observationId);
  const history = useReviews({ observation_id: observationId, page_size: 20 });
  const createReview = useCreateReview();
  const [decision, setDecision] = useState<Decision | null>(null);
  const [corrType, setCorrType] = useState('');
  const [corrCondition, setCorrCondition] = useState('');
  const [corrSeverity, setCorrSeverity] = useState('');
  const [comment, setComment] = useState('');
  const [error, setError] = useState<string | null>(null);

  const o = obs.data;
  const style = o ? bboxStyle(o) : null;

  useEffect(() => {
    if (!canMutate) return;
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      const d = DECISIONS.find((x) => x.key === e.key);
      if (d) setDecision(d.id);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [canMutate]);

  if (!o) return null;
  const Icon = assetTypeIcon(o.object_type);
  const unresolvedDedup = o.dedup_result === 'POSSIBLE_MATCH' || o.dedup_result === 'AMBIGUOUS';

  const submit = async () => {
    if (!decision) return;
    setError(null);
    if (decision === 'CORRECTED' && !corrType && !corrCondition && !corrSeverity) {
      setError('Для корректировки укажите хотя бы одно исправление.');
      return;
    }
    const payload: ReviewCreate = {
      observation_id: o.id,
      decision,
      comment: comment.trim() || undefined,
    };
    if (decision === 'CORRECTED') {
      if (corrType) payload.corrected_asset_type = corrType;
      if (corrCondition) payload.corrected_condition = corrCondition;
      if (corrSeverity) payload.corrected_severity = Number(corrSeverity);
    }
    try {
      await createReview.mutateAsync(payload);
      toast('success', `Решение «${label.reviewDecision(decision)}» сохранено.`);
      setDecision(null);
      setComment('');
      setCorrType('');
      setCorrCondition('');
      setCorrSeverity('');
      onDone();
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-5)' }}>
      <section className="panel" aria-label="Карточка проверки">
        <div className="panel-head">
          <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <Icon style={{ color: 'var(--accent)' }} />
            <h2 className="panel-title">{label.assetType(o.object_type)} · {label.condition(o.condition_class)}</h2>
          </span>
          <span style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <Status tone={dedupTone[o.dedup_result ?? ''] ?? 'neutral'} shape="square">{label.dedup(o.dedup_result)}</Status>
            <Link className="link small" to={`/app/observations/${o.id}`}>подробно</Link>
          </span>
        </div>
        <div className="panel-body">
          {unresolvedDedup && (
            <div className="login-error" style={{ background: 'var(--warn-soft)', borderColor: 'rgba(240,164,92,0.4)', color: 'var(--warn)', marginBottom: 'var(--sp-4)' }} role="note">
              <IconAlert className="icon-sm" style={{ display: 'inline', verticalAlign: '-2px', marginRight: 6 }} />
              Дедупликация не разрешила совпадение автоматически. Проверьте, относится ли обнаружение к существующему объекту
              {o.asset_id ? '' : ' — объект ещё не создан'}.
            </div>
          )}
          <div className="detail-grid review-card-grid">
            <div>
              {o.image_url && !imgFailed ? (
                <div className="frame-view">
                  <img src={o.image_url} alt="Кадр наблюдения" onError={onImgError} />
                  {style && (
                    <div className="frame-bbox" style={style}>
                      <span className="frame-bbox-label">{o.object_type} {fmtPercent(o.detector_confidence, 0)}</span>
                    </div>
                  )}
                </div>
              ) : (
                <EmptyState title="Кадр недоступен">Решение можно принять по метаданным; ссылка на кадр могла истечь.</EmptyState>
              )}
              <p className="faint" style={{ fontSize: 'var(--text-micro)', marginTop: 8 }}>
                Анонимизация не применялась (MVP). Кадр показан как есть.
              </p>
            </div>
            <div>
              <KeyValue
                items={[
                  ['Наблюдение', fmtDateTime(o.observed_at)],
                  ['Уверенность детектора', <span className="num">{fmtPercent(o.detector_confidence, 1)}</span>],
                  ['Уверенность классификатора', <span className="num">{fmtPercent(o.classifier_confidence, 1)}</span>],
                  ['Тяжесть (ML)', <Severity value={o.severity} />],
                  ['Модель', <span className="mono small">{o.model_name} {o.model_version}</span>],
                  ['Объект', o.asset_id ? <Link className="link" to={`/app/assets/${o.asset_id}`}>паспорт</Link> : 'не сопоставлен'],
                  ['Координаты', <span className="mono small">{o.longitude != null && o.latitude != null ? `${o.latitude.toFixed(5)}, ${o.longitude.toFixed(5)}` : 'нет GPS'}</span>],
                ]}
              />
            </div>
          </div>
        </div>
      </section>

      <section className="panel" aria-label="Решение оператора">
        <div className="panel-head">
          <h2 className="panel-title">Решение</h2>
          <span className="faint small">клавиши 1–4 · Enter не используется</span>
        </div>
        <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' }}>
          {!canMutate && (
            <p className="small" style={{ color: 'var(--warn)' }}>
              Режим только чтения: решения доступны OPERATOR / ADMIN.
            </p>
          )}
          {error && <div className="login-error" role="alert">{error}</div>}
          <div className="review-decisions" role="group" aria-label="Варианты решения">
            {DECISIONS.map((d) => (
              <button
                key={d.id}
                className={`decision-btn ${d.cls}`}
                aria-pressed={decision === d.id}
                disabled={!canMutate}
                onClick={() => setDecision(decision === d.id ? null : d.id)}
                style={decision === d.id ? { borderColor: 'var(--accent)', background: 'var(--accent-soft)' } : undefined}
              >
                <span className="decision-name">
                  {d.id === 'CONFIRMED' && <IconCheck className="icon-sm" style={{ display: 'inline', verticalAlign: '-2px', marginRight: 4, color: 'var(--ok)' }} />}
                  {d.id === 'REJECTED' && <IconClose className="icon-sm" style={{ display: 'inline', verticalAlign: '-2px', marginRight: 4, color: 'var(--crit)' }} />}
                  {d.name} <span className="faint mono">[{d.key}]</span>
                </span>
                <span className="decision-hint">{d.hint}</span>
              </button>
            ))}
          </div>

          {decision === 'CORRECTED' && (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 'var(--sp-3)' }}>
              <Field label="Исправленный тип">
                <select className="select" value={corrType} onChange={(e) => setCorrType(e.target.value)}>
                  <option value="">Без изменения</option>
                  {assetTypeOptions.map((t) => <option key={t.value} value={t.value}>{t.name}</option>)}
                </select>
              </Field>
              <Field label="Исправленное состояние">
                <select className="select" value={corrCondition} onChange={(e) => setCorrCondition(e.target.value)}>
                  <option value="">Без изменения</option>
                  {conditionOptions.map((c) => <option key={c.value} value={c.value}>{c.name}</option>)}
                </select>
              </Field>
              <Field label="Исправленная тяжесть">
                <select className="select" value={corrSeverity} onChange={(e) => setCorrSeverity(e.target.value)}>
                  <option value="">Без изменения</option>
                  {[1, 2, 3, 4, 5].map((s) => <option key={s} value={s}>S{s}</option>)}
                </select>
              </Field>
            </div>
          )}

          <Field label="Комментарий (необязательно)">
            <textarea className="textarea" value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Основание решения, контекст объезда…" />
          </Field>

          <div style={{ display: 'flex', gap: 'var(--sp-3)', alignItems: 'center' }}>
            <Button variant="primary" disabled={!decision || !canMutate} loading={createReview.isPending} onClick={() => void submit()}>
              Сохранить решение
            </Button>
            <span className="faint small">
              {decision ? `Будет записано: ${label.reviewDecision(decision)}` : 'Выберите вариант решения'}
            </span>
          </div>
        </div>
      </section>

      <section className="panel" aria-label="Предыдущие решения">
        <div className="panel-head">
          <h2 className="panel-title">Предыдущие решения</h2>
          <Badge>append-only</Badge>
        </div>
        {history.isPending && <LoadingState />}
        {history.data && history.data.items.length === 0 && (
          <p className="muted small" style={{ padding: 'var(--sp-4) var(--sp-5)' }}>Решений по этому наблюдению ещё не было.</p>
        )}
        {history.data && history.data.items.length > 0 && (
          <div className="table-wrap">
            <table className="table">
              <thead>
                <tr><th>Время</th><th>Решение</th><th>Комментарий</th></tr>
              </thead>
              <tbody>
                {history.data.items.map((r) => (
                  <tr key={r.id}>
                    <td className="muted">{fmtDateTime(r.reviewed_at ?? r.created_at)}</td>
                    <td>{label.reviewDecision(r.decision)}</td>
                    <td className="muted small">{r.comment ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}