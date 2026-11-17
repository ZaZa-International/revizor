import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useJob, useJobAction, useJobFrames } from '../data/hooks';
import { Badge, Button, Dialog, EmptyState, ErrorState, KeyValue, LoadingState, Pagination, Progress, Status, toast } from '../components/ui';
import { IconChevronLeft } from '../components/icons';
import { jobStatusTone, label } from '../lib/labels';
import { fmtDateTime, fmtNumber } from '../lib/format';
import { errorMessage } from '../api/client';
import { usePermissions } from '../lib/permissions';

const STAGES = [
  'VALIDATION', 'STORAGE', 'FRAME_EXTRACTION', 'QUALITY_GATE', 'PRIVACY_FILTER',
  'INFERENCE', 'NORMALIZATION', 'TRACKING', 'GEOLOCATION', 'DEDUPLICATION',
  'RISK_SCORING', 'PERSISTENCE', 'COMPLETED',
];

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { canMutate } = usePermissions();
  const job = useJob(id);
  const retry = useJobAction('retry');
  const cancel = useJobAction('cancel');
  const [framePage, setFramePage] = useState(1);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const frames = useJobFrames(id, framePage);

  if (job.isPending) return <LoadingState label="Загрузка задачи…" />;
  if (job.error) return <ErrorState error={job.error} onRetry={() => job.refetch()} />;
  const j = job.data!;
  const active = ['PENDING', 'QUEUED', 'PROCESSING'].includes(j.status);
  const canRetry = ['FAILED', 'PARTIALLY_COMPLETED', 'CANCELLED'].includes(j.status);
  const stageIdx = STAGES.indexOf(j.current_stage ?? '');

  const act = async (kind: 'retry' | 'cancel') => {
    try {
      await (kind === 'retry' ? retry : cancel).mutateAsync(j.id);
      toast('success', kind === 'retry' ? 'Задача перезапущена.' : 'Задача отменена.');
    } catch (err) {
      toast('error', errorMessage(err));
    }
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <Link className="link small" to="/app/jobs">
            <IconChevronLeft className="icon-sm" style={{ display: 'inline', verticalAlign: '-2px' }} /> Задачи
          </Link>
          <h1 style={{ marginTop: 8 }}>
            Задача <span className="mono">{j.id.slice(0, 8)}</span>
          </h1>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 10 }}>
            <Status tone={jobStatusTone[j.status] ?? 'neutral'}>{label.jobStatus(j.status)}</Status>
            <Badge>стадия: {label.jobStage(j.current_stage)}</Badge>
            {active && <Badge tone="accent">polling 1.5 с</Badge>}
          </div>
        </div>
        <div className="page-head-actions">
          <Link className="btn" to={`/app/observations?job_id=${j.id}`}>Результаты</Link>
          {canMutate && canRetry && (
            <Button loading={retry.isPending} onClick={() => void act('retry')}>Перезапустить</Button>
          )}
          {canMutate && active && (
            <Button variant="danger" loading={cancel.isPending} onClick={() => setConfirmCancel(true)}>Отменить</Button>
          )}
        </div>
      </div>

      {j.error_code && (
        <div className="login-error" role="alert" style={{ marginBottom: 'var(--sp-5)' }}>
          <strong>{j.error_code}</strong>: {j.error_message ?? 'Ошибка обработки.'}
          {canRetry && ' Повторный запуск обработает только необработанные кадры (идемпотентно).'}
        </div>
      )}

      <div className="detail-grid">
        <section className="panel" aria-label="Прогресс">
          <div className="panel-head">
            <h2 className="panel-title">Прогресс</h2>
            <span className="num">{Math.round(j.progress * 100)}%</span>
          </div>
          <div className="panel-body">
            <Progress value={j.progress} tone={j.status === 'FAILED' ? 'crit' : j.status === 'PARTIALLY_COMPLETED' ? 'warn' : undefined} />
            <div className="factor-grid" style={{ marginTop: 'var(--sp-4)' }}>
              <div className="factor">
                <div className="factor-label">Обработано</div>
                <div className="factor-value">{fmtNumber(j.processed_frames)}</div>
              </div>
              <div className="factor">
                <div className="factor-label">Всего кадров</div>
                <div className="factor-value">{fmtNumber(j.total_frames)}</div>
              </div>
              <div className="factor">
                <div className="factor-label">Ошибки</div>
                <div className="factor-value" style={{ color: j.failed_frames > 0 ? 'var(--crit)' : undefined }}>{fmtNumber(j.failed_frames)}</div>
              </div>
              <div className="factor">
                <div className="factor-label">Отклонено</div>
                <div className="factor-value" style={{ color: j.rejected_frames > 0 ? 'var(--warn)' : undefined }}>{fmtNumber(j.rejected_frames)}</div>
              </div>
            </div>
            <hr className="divider" />
            <p className="eyebrow" style={{ marginBottom: 10 }}>Стадии pipeline</p>
            <div className="stage-track">
              {STAGES.map((s, i) => (
                <span key={s} className={`stage-chip${i < stageIdx ? ' done' : i === stageIdx ? ' current' : ''}`}>
                  {label.jobStage(s)}
                </span>
              ))}
            </div>
          </div>
        </section>

        <section className="panel" aria-label="Параметры задачи">
          <div className="panel-head">
            <h2 className="panel-title">Параметры</h2>
          </div>
          <div className="panel-body">
            <KeyValue
              items={[
                ['Идентификатор', <span className="mono small">{j.id}</span>],
                ['Загрузка', <Link className="link mono small" to="/app/jobs">{j.upload_id.slice(0, 8)}</Link>],
                ['Маршрут', j.route_id ? <Link className="link mono small" to={`/app/routes/${j.route_id}`}>{j.route_id.slice(0, 8)}</Link> : '—'],
                ['Создана', fmtDateTime(j.created_at)],
                ['Старт', fmtDateTime(j.started_at)],
                ['Завершена', fmtDateTime(j.finished_at)],
              ]}
            />
            <p className="faint small" style={{ marginTop: 14 }}>
              Покадровые ошибки не валят задачу: итог COMPLETED / PARTIALLY_COMPLETED / FAILED.
              Повторный запуск пропускает обработанные кадры.
            </p>
          </div>
        </section>
      </div>

      <section className="panel" style={{ marginTop: 'var(--sp-5)' }} aria-label="Покадровые результаты">
        <div className="panel-head">
          <h2 className="panel-title">Кадры</h2>
        </div>
        {frames.isPending && <LoadingState />}
        {frames.error && <ErrorState error={frames.error} onRetry={() => frames.refetch()} />}
        {frames.data && frames.data.items.length === 0 && <EmptyState title="Кадров пока нет" />}
        {frames.data && frames.data.items.length > 0 && (
          <>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>№</th>
                    <th>Статус</th>
                    <th>Причина отклонения / ошибка</th>
                    <th>Время кадра</th>
                  </tr>
                </thead>
                <tbody>
                  {frames.data.items.map((f) => (
                    <tr key={f.id}>
                      <td className="num">{f.frame_index}</td>
                      <td>
                        <Status tone={f.status === 'PROCESSED' ? 'ok' : f.status === 'FAILED' ? 'crit' : f.status === 'REJECTED' ? 'warn' : 'neutral'} shape="square">
                          {label.frameStatus(f.status)}
                        </Status>
                      </td>
                      <td className="muted small">
                        {f.status === 'REJECTED' ? (f.reject_reason ?? 'quality gate') : f.status === 'FAILED' ? (f.error_code ?? 'ошибка') : '—'}
                      </td>
                      <td className="muted">{fmtDateTime(f.observed_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={frames.data.page} pages={frames.data.pages} total={frames.data.total} pageSize={frames.data.page_size}
              onPage={setFramePage} noun={['кадр', 'кадра', 'кадров']} />
          </>
        )}
      </section>

      <Dialog
        open={confirmCancel}
        onClose={() => setConfirmCancel(false)}
        title="Отменить задачу?"
        footer={
          <>
            <Button onClick={() => setConfirmCancel(false)}>Не отменять</Button>
            <Button
              variant="danger"
              loading={cancel.isPending}
              onClick={() => {
                setConfirmCancel(false);
                void act('cancel');
              }}
            >
              Отменить задачу
            </Button>
          </>
        }
      >
        <p>
          Обработка кадров будет остановлена. Уже обработанные кадры и наблюдения сохранятся;
          незавершённые кадры можно будет обработать повторным запуском (идемпотентно).
        </p>
      </Dialog>
    </div>
  );
}