import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useAsset, useDefect, useObservations, usePatchDefect } from '../data/hooks';
import { Badge, Button, EmptyState, ErrorState, Field, KeyValue, LoadingState, Severity, Status, toast } from '../components/ui';
import { IconChevronLeft } from '../components/icons';
import { defectStatusOptions, defectStatusTone, label, reviewStatusTone } from '../lib/labels';
import { fmtDateTime, fmtNumber } from '../lib/format';
import { errorMessage } from '../api/client';
import { usePermissions } from '../lib/permissions';
import type { Defect } from '../api/types';

export default function DefectDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { canMutate } = usePermissions();
  const defect = useDefect(id);

  if (defect.isPending) return <LoadingState label="Загрузка дефекта…" />;
  if (defect.error) return <ErrorState error={defect.error} onRetry={() => defect.refetch()} />;
  const d = defect.data!;

  return (
    <div>
      <div className="page-head">
        <div>
          <Link className="link small" to="/app/defects">
            <IconChevronLeft className="icon-sm" style={{ display: 'inline', verticalAlign: '-2px' }} /> Дефекты
          </Link>
          <h1 style={{ marginTop: 8 }}>{label.defectType(d.defect_type)}</h1>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 10 }}>
            <Status tone={defectStatusTone[d.status] ?? 'neutral'}>{label.defectStatus(d.status)}</Status>
            <Severity value={d.severity} />
            <Badge>наблюдений: {d.observation_count ?? '—'}</Badge>
          </div>
        </div>
      </div>

      <div className="detail-grid">
        <section className="panel" aria-label="Карточка дефекта">
          <div className="panel-head">
            <h2 className="panel-title">Карточка</h2>
            <span className="mono faint small">{d.id.slice(0, 8)}</span>
          </div>
          <div className="panel-body">
            <KeyValue
              items={[
                ['Объект', d.asset_id ? <Link className="link" to={`/app/assets/${d.asset_id}`}>паспорт объекта</Link> : '—'],
                ['Первое обнаружение', fmtDateTime(d.first_detected_at)],
                ['Последнее обнаружение', fmtDateTime(d.last_detected_at)],
                ['Устранён', d.resolved_at ? fmtDateTime(d.resolved_at) : '—'],
                ['Повторяемость', <span className="num">{fmtNumber(d.observation_count ?? 0)} наблюдений</span>],
                ['Описание', d.description ?? '—'],
              ]}
            />
            <hr className="divider" />
            <p className="faint small">
              Тяжесть (S1–S5) отражает масштаб повреждения. Приоритет обработки объекта рассчитывается отдельно
              (severity × impact × confidence) и виден в паспорте объекта.
            </p>
          </div>
        </section>

        {canMutate ? (
          <DefectEditPanel defect={d} />
        ) : (
          <section className="panel" aria-label="Действия">
            <div className="panel-body">
              <EmptyState title="Только чтение">
                Изменение статуса и тяжести дефекта доступно операторам и администраторам.
              </EmptyState>
            </div>
          </section>
        )}
      </div>

      {d.asset_id && <RelatedObservations assetId={d.asset_id} />}
    </div>
  );
}

function DefectEditPanel({ defect }: { defect: Defect }) {
  const patch = usePatchDefect();
  const [status, setStatus] = useState(defect.status);
  const [severity, setSeverity] = useState(defect.severity != null ? String(defect.severity) : '');
  const [description, setDescription] = useState(defect.description ?? '');
  const [error, setError] = useState<string | null>(null);

  const dirty =
    status !== defect.status ||
    (severity !== '' && Number(severity) !== defect.severity) ||
    description !== (defect.description ?? '');

  const submit = async () => {
    setError(null);
    const body: Record<string, unknown> = {};
    if (status !== defect.status) body.status = status;
    if (severity !== '' && Number(severity) !== defect.severity) body.severity = Number(severity);
    if (description !== (defect.description ?? '')) body.description = description;
    try {
      await patch.mutateAsync({ id: defect.id, patch: body as never });
      toast('success', 'Дефект обновлён.');
    } catch (err) {
      setError(errorMessage(err));
    }
  };

  return (
    <section className="panel" aria-label="Управление дефектом">
      <div className="panel-head">
        <h2 className="panel-title">Управление</h2>
      </div>
      <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' }}>
        {error && <div className="login-error" role="alert">{error}</div>}
        <Field label="Статус">
          <select className="select" value={status} onChange={(e) => setStatus(e.target.value as Defect['status'])}>
            {defectStatusOptions.map((s) => <option key={s.value} value={s.value}>{s.name}</option>)}
          </select>
        </Field>
        <Field label="Тяжесть (1–5)">
          <select className="select" value={severity} onChange={(e) => setSeverity(e.target.value)}>
            <option value="">Не задана</option>
            {[1, 2, 3, 4, 5].map((s) => <option key={s} value={s}>S{s}</option>)}
          </select>
        </Field>
        <Field label="Описание">
          <textarea className="textarea" value={description} onChange={(e) => setDescription(e.target.value)} />
        </Field>
        <Button variant="primary" disabled={!dirty} loading={patch.isPending} onClick={() => void submit()}>
          Сохранить изменения
        </Button>
      </div>
    </section>
  );
}

function RelatedObservations({ assetId }: { assetId: string }) {
  const navigate = useNavigate();
  const q = useObservations({ asset_id: assetId, page_size: 10 });
  const asset = useAsset(assetId);
  return (
    <section className="panel" style={{ marginTop: 'var(--sp-5)' }} aria-label="Наблюдения объекта">
      <div className="panel-head">
        <h2 className="panel-title">Наблюдения объекта {asset.data?.display_name ? `· ${asset.data.display_name}` : ''}</h2>
        <Link className="link small" to={`/app/observations?asset_id=${assetId}`}>все</Link>
      </div>
      {q.isPending && <LoadingState />}
      {q.error && <ErrorState error={q.error} onRetry={() => q.refetch()} />}
      {q.data && q.data.items.length === 0 && <EmptyState title="Наблюдений нет" />}
      {q.data && q.data.items.length > 0 && (
        <div className="table-wrap">
          <table className="table">
            <thead>
              <tr>
                <th>Время</th>
                <th>Состояние</th>
                <th>Тяжесть</th>
                <th>Уверенность</th>
                <th>Проверка</th>
              </tr>
            </thead>
            <tbody>
              {q.data.items.map((o) => (
                <tr key={o.id} className="clickable" onClick={() => navigate(`/app/observations/${o.id}`)}>
                  <td className="muted">{fmtDateTime(o.observed_at)}</td>
                  <td>{label.condition(o.effective_condition ?? o.condition_class)}</td>
                  <td><Severity value={o.effective_severity ?? o.severity} /></td>
                  <td className="num">{o.detector_confidence != null ? `${Math.round(o.detector_confidence * 100)}%` : '—'}</td>
                  <td><Status tone={reviewStatusTone[o.review_status] ?? 'neutral'}>{label.reviewStatus(o.review_status)}</Status></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <p className="faint" style={{ fontSize: 'var(--text-micro)', padding: '10px 20px' }}>
        Показаны наблюдения объекта; связь дефекта с конкретными кадрами хранится в журнале наблюдений (observation_count дефекта).
      </p>
    </section>
  );
}