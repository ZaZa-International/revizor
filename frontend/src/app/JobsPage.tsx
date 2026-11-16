import { useRef, useState, type DragEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useCreateJob, useJobs, useRoutes, useUploads } from '../data/hooks';
import { useDataSource } from '../data/source';
import { usePermissions } from '../lib/permissions';
import { uploadWithProgress } from '../api/uploads';
import { demoProvider } from '../demo/provider';
import { Button, EmptyState, ErrorState, Field, LoadingState, Pagination, Progress, Status, toast } from '../components/ui';
import { IconJob, IconUpload } from '../components/icons';
import { jobStatusTone, label } from '../lib/labels';
import { fmtBytes, fmtDateTime, fmtNumber } from '../lib/format';
import { errorMessage } from '../api/client';

const ACCEPT = '.jpg,.jpeg,.png,.webp,.mp4,.avi,.mov,.webm';

export default function JobsPage() {
  const navigate = useNavigate();
  const { isDemo } = useDataSource();
  const { canMutate } = usePermissions();
  const [page, setPage] = useState(1);
  const jobs = useJobs({ page, page_size: 15 });
  const uploads = useUploads({ page_size: 6 });
  const routes = useRoutes({ page_size: 50 });
  const createJob = useCreateJob();

  const [file, setFile] = useState<File | null>(null);
  const [routeId, setRouteId] = useState('');
  const [autoStart, setAutoStart] = useState(true);
  const [dragover, setDragover] = useState(false);
  const [progress, setProgress] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const pick = (f: File | null | undefined) => {
    setError(null);
    if (!f) return;
    const ok = /\.(jpe?g|png|webp|mp4|avi|mov|webm)$/i.test(f.name);
    if (!ok) {
      setError('Допустимые форматы: jpeg/png/webp, mp4/avi/mov/webm.');
      return;
    }
    setFile(f);
  };

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragover(false);
    pick(e.dataTransfer.files?.[0]);
  };

  const start = async () => {
    if (!file) return;
    setBusy(true);
    setError(null);
    setProgress(isDemo ? null : 0);
    try {
      const result = isDemo
        ? await demoProvider.createUpload(file, routeId || undefined)
        : await uploadWithProgress(file, routeId || undefined, setProgress);
      setProgress(1);
      toast('success', result.created ? `Файл «${file.name}» загружен.` : 'Дубликат по checksum — использована существующая загрузка.');
      if (autoStart) {
        const job = await createJob.mutateAsync({ upload_id: result.upload.id, route_id: routeId || undefined });
        toast('info', 'Задача обработки создана.');
        navigate(`/app/jobs/${job.id}`);
      } else {
        void uploads.refetch();
      }
      setFile(null);
      setProgress(null);
    } catch (err) {
      setError(errorMessage(err));
      setProgress(null);
    } finally {
      setBusy(false);
    }
  };

  const runJob = async (uploadId: string) => {
    try {
      const job = await createJob.mutateAsync({ upload_id: uploadId });
      toast('info', 'Задача обработки создана.');
      navigate(`/app/jobs/${job.id}`);
    } catch (err) {
      toast('error', errorMessage(err));
    }
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <p className="eyebrow">Обработка</p>
          <h1>Задачи обработки</h1>
          <p className="page-desc">
            Загрузите фото или видео объезда → система извлечёт кадры, проверит качество, выполнит детекцию, дедупликацию и оценку риска.
          </p>
        </div>
      </div>

      <div className="detail-grid" style={{ marginBottom: 'var(--sp-5)' }}>
        <section className="panel" aria-label="Загрузка материалов">
          <div className="panel-head">
            <h2 className="panel-title">Новая загрузка</h2>
            {!canMutate && !isDemo && <span className="badge">только чтение</span>}
          </div>
          <div className="panel-body" style={{ display: 'flex', flexDirection: 'column', gap: 'var(--sp-4)' }}>
            {error && <div className="login-error" role="alert">{error}</div>}
            <div
              className={`upload-zone${dragover ? ' dragover' : ''}`}
              role="button"
              tabIndex={0}
              aria-label="Выбрать файл или перетащить сюда"
              onClick={() => inputRef.current?.click()}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); inputRef.current?.click(); } }}
              onDragOver={(e) => { e.preventDefault(); setDragover(true); }}
              onDragLeave={() => setDragover(false)}
              onDrop={onDrop}
            >
              <IconUpload />
              {file ? (
                <>
                  <span className="cell-main">{file.name}</span>
                  <span className="muted small">{fmtBytes(file.size)} · нажмите, чтобы заменить</span>
                </>
              ) : (
                <>
                  <span className="cell-main">Перетащите файл сюда или нажмите для выбора</span>
                  <span className="muted small">jpeg / png / webp · mp4 / avi / mov / webm · до 2 ГБ</span>
                </>
              )}
              <input
                ref={inputRef}
                type="file"
                accept={ACCEPT}
                hidden
                onChange={(e) => pick(e.target.files?.[0])}
              />
            </div>

            {progress !== null && (
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span className="small muted">Загрузка на сервер</span>
                  <span className="num small">{Math.round(progress * 100)}%</span>
                </div>
                <Progress value={progress} />
              </div>
            )}

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--sp-3)', alignItems: 'end' }}>
              <Field label="Маршрут (необязательно)">
                <select className="select" value={routeId} onChange={(e) => setRouteId(e.target.value)}>
                  <option value="">Без маршрута</option>
                  {routes.data?.items.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
                </select>
              </Field>
              <label style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 'var(--text-small)', paddingBottom: 8 }}>
                <input type="checkbox" checked={autoStart} onChange={(e) => setAutoStart(e.target.checked)} />
                Сразу запустить обработку
              </label>
            </div>

            <Button variant="primary" disabled={!file || busy || (!canMutate && !isDemo)} loading={busy} onClick={() => void start()}>
              {busy ? 'Обработка…' : 'Загрузить'}
            </Button>
            <p className="faint" style={{ fontSize: 'var(--text-micro)' }}>
              GPS-трек можно передать в metadata загрузки (см. контракт API). Без GPS объекты создаются со статусом UNAVAILABLE — координаты не выдумываются.
            </p>
          </div>
        </section>

        <section className="panel" aria-label="Последние загрузки">
          <div className="panel-head">
            <h2 className="panel-title">Последние загрузки</h2>
          </div>
          {uploads.isPending && <LoadingState />}
          {uploads.error && <ErrorState error={uploads.error} onRetry={() => uploads.refetch()} />}
          {uploads.data && uploads.data.items.length === 0 && (
            <EmptyState title="Загрузок пока нет">Материалы объездов появятся здесь после загрузки.</EmptyState>
          )}
          {uploads.data && uploads.data.items.length > 0 && (
            <div className="attention-list">
              {uploads.data.items.map((u) => (
                <div key={u.id} className="attention-item">
                  <IconJob style={{ color: 'var(--muted)' }} />
                  <span className="att-main">
                    <span className="att-title">{u.original_filename}</span>
                    <span className="att-sub">
                      {u.media_type === 'VIDEO' ? 'видео' : 'изображение'} · {fmtBytes(u.file_size)} · {fmtDateTime(u.created_at)}
                    </span>
                  </span>
                  {(canMutate || isDemo) && (
                    <Button size="sm" loading={createJob.isPending} onClick={() => void runJob(u.id)}>
                      Обработать
                    </Button>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      <section className="panel" aria-label="Список задач">
        <div className="panel-head">
          <h2 className="panel-title">Задачи</h2>
          <span className="faint small">polling активных задач каждые 2 с</span>
        </div>
        {jobs.isPending && <LoadingState />}
        {jobs.error && <ErrorState error={jobs.error} onRetry={() => jobs.refetch()} />}
        {jobs.data && jobs.data.items.length === 0 && (
          <EmptyState title="Задач нет">Загрузите материалы и запустите обработку.</EmptyState>
        )}
        {jobs.data && jobs.data.items.length > 0 && (
          <>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Задача</th>
                    <th>Статус</th>
                    <th style={{ minWidth: 160 }}>Прогресс</th>
                    <th>Кадры</th>
                    <th>Создана</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.data.items.map((j) => (
                    <tr key={j.id} className="clickable" tabIndex={0}
                      onClick={() => navigate(`/app/jobs/${j.id}`)}
                      onKeyDown={(e) => { if (e.key === 'Enter') navigate(`/app/jobs/${j.id}`); }}
                    >
                      <td>
                        <span className="cell-main mono">{j.id.slice(0, 8)}</span>
                        <span className="cell-sub">{label.jobStage(j.current_stage)}</span>
                      </td>
                      <td><Status tone={jobStatusTone[j.status] ?? 'neutral'}>{label.jobStatus(j.status)}</Status></td>
                      <td>
                        <Progress value={j.progress} tone={j.status === 'FAILED' ? 'crit' : j.status === 'PARTIALLY_COMPLETED' ? 'warn' : undefined} />
                        <span className="num faint" style={{ fontSize: 'var(--text-micro)' }}>{Math.round(j.progress * 100)}%</span>
                      </td>
                      <td>
                        <span className="num">{fmtNumber(j.processed_frames)}/{fmtNumber(j.total_frames)}</span>
                        {(j.failed_frames > 0 || j.rejected_frames > 0) && (
                          <span className="cell-sub">ошибки: {j.failed_frames} · отклонено: {j.rejected_frames}</span>
                        )}
                      </td>
                      <td className="muted">{fmtDateTime(j.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={jobs.data.page} pages={jobs.data.pages} total={jobs.data.total} pageSize={jobs.data.page_size}
              onPage={setPage} noun={['задача', 'задачи', 'задач']} />
          </>
        )}
      </section>
    </div>
  );
}