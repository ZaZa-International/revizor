import { useNavigate, useSearchParams } from 'react-router-dom';
import { useObservations } from '../data/hooks';
import { EmptyState, ErrorState, LoadingState, Pagination, Severity, Status } from '../components/ui';
import { assetTypeIcon } from '../components/icons';
import { assetTypeOptions, dedupOptions, dedupTone, label, reviewStatusOptions, reviewStatusTone } from '../lib/labels';
import { fmtDateTime, fmtPercent } from '../lib/format';

export default function ObservationsPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const page = Number(params.get('page') ?? 1);
  const reviewStatus = params.get('review_status') ?? '';
  const dedup = params.get('dedup_result') ?? '';
  const objectType = params.get('object_type') ?? '';
  const assetId = params.get('asset_id') ?? '';
  const jobId = params.get('job_id') ?? '';

  const query = useObservations({
    page,
    page_size: 20,
    review_status: reviewStatus || undefined,
    dedup_result: dedup || undefined,
    object_type: objectType || undefined,
    asset_id: assetId || undefined,
    job_id: jobId || undefined,
  });

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== 'page') next.delete('page');
    setParams(next, { replace: true });
  };

  return (
    <div>
      <div className="page-head">
        <div>
          <p className="eyebrow">Реестр наблюдений</p>
          <h1>Наблюдения</h1>
          <p className="page-desc">
            Каждое обнаружение объекта на кадре: исходное предсказание ML, эффективное состояние после проверки, геопривязка и дедупликация.
          </p>
        </div>
      </div>

      {(assetId || jobId) && (
        <p className="small muted" style={{ marginBottom: 'var(--sp-3)' }}>
          Фильтр: {assetId && <>объект <span className="mono">{assetId.slice(0, 8)}</span></>}
          {jobId && <>задача <span className="mono">{jobId.slice(0, 8)}</span></>}
          {' · '}
          <button className="link" onClick={() => { setParam('asset_id', ''); setParam('job_id', ''); }}>
            сбросить
          </button>
        </p>
      )}

      <div className="filter-bar">
        <div className="chip-row" role="group" aria-label="Статус проверки">
          <button className="chip" aria-pressed={reviewStatus === ''} onClick={() => setParam('review_status', '')}>Все</button>
          {reviewStatusOptions.map((s) => (
            <button key={s.value} className="chip" aria-pressed={reviewStatus === s.value} onClick={() => setParam('review_status', s.value)}>
              {s.name}
            </button>
          ))}
        </div>
      </div>
      <div className="filter-bar">
        <select className="select" value={objectType} onChange={(e) => setParam('object_type', e.target.value)} aria-label="Тип объекта">
          <option value="">Все типы</option>
          {assetTypeOptions.map((t) => <option key={t.value} value={t.value}>{t.name}</option>)}
        </select>
        <select className="select" value={dedup} onChange={(e) => setParam('dedup_result', e.target.value)} aria-label="Результат дедупликации">
          <option value="">Любая дедупликация</option>
          {dedupOptions.map((d) => <option key={d.value} value={d.value}>{d.name}</option>)}
        </select>
      </div>

      <div className="panel">
        {query.isPending && <LoadingState />}
        {query.error && <ErrorState error={query.error} onRetry={() => query.refetch()} />}
        {query.data && query.data.items.length === 0 && (
          <EmptyState title="Наблюдения не найдены">
            Наблюдения появляются после обработки загруженных материалов. Измените фильтры или запустите задачу обработки.
          </EmptyState>
        )}
        {query.data && query.data.items.length > 0 && (
          <>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Кадр</th>
                    <th>Объект / состояние</th>
                    <th>Уверенность</th>
                    <th>Тяжесть</th>
                    <th>Дедупликация</th>
                    <th>Проверка</th>
                    <th>Время</th>
                  </tr>
                </thead>
                <tbody>
                  {query.data.items.map((o) => {
                    const Icon = assetTypeIcon(o.object_type);
                    return (
                      <tr key={o.id} className="clickable" tabIndex={0}
                        onClick={() => navigate(`/app/observations/${o.id}`)}
                        onKeyDown={(e) => { if (e.key === 'Enter') navigate(`/app/observations/${o.id}`); }}
                      >
                        <td>
                          {o.crop_url ? (
                            <img src={o.crop_url} alt="" loading="lazy" style={{ width: 76, height: 46, objectFit: 'cover', borderRadius: 3, border: '1px solid var(--line-soft)' }} />
                          ) : (
                            <span className="faint small">нет кадра</span>
                          )}
                        </td>
                        <td>
                          <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <Icon style={{ color: 'var(--muted)' }} />
                            <span>
                              <span className="cell-main">{label.assetType(o.object_type)}</span>
                              <span className="cell-sub">{label.condition(o.effective_condition ?? o.condition_class)}</span>
                            </span>
                          </span>
                        </td>
                        <td className="num">{fmtPercent(o.detector_confidence, 0)}</td>
                        <td><Severity value={o.effective_severity ?? o.severity} /></td>
                        <td><Status tone={dedupTone[o.dedup_result ?? ''] ?? 'neutral'} shape="square">{label.dedup(o.dedup_result)}</Status></td>
                        <td><Status tone={reviewStatusTone[o.review_status] ?? 'neutral'}>{label.reviewStatus(o.review_status)}</Status></td>
                        <td className="muted">{fmtDateTime(o.observed_at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Pagination page={query.data.page} pages={query.data.pages} total={query.data.total} pageSize={query.data.page_size}
              onPage={(p) => setParam('page', String(p))} noun={['наблюдение', 'наблюдения', 'наблюдений']} />
          </>
        )}
      </div>
    </div>
  );
}