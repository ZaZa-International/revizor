import { useNavigate, useSearchParams } from 'react-router-dom';
import { useDefects } from '../data/hooks';
import { EmptyState, ErrorState, LoadingState, Pagination, Severity, Status } from '../components/ui';
import { defectStatusOptions, defectStatusTone, defectTypeOptions, label } from '../lib/labels';
import { fmtDateTime, fmtRelative } from '../lib/format';

export default function DefectsPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const page = Number(params.get('page') ?? 1);
  const status = params.get('status') ?? '';
  const defectType = params.get('defect_type') ?? '';
  const severityMin = params.get('severity_min') ?? '';
  const assetId = params.get('asset_id') ?? '';

  const query = useDefects({
    page,
    page_size: 20,
    status: status || undefined,
    defect_type: defectType || undefined,
    severity_min: severityMin || undefined,
    asset_id: assetId || undefined,
    sort_by: 'severity',
    order: 'desc',
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
          <p className="eyebrow">Инциденты</p>
          <h1>Дефекты</h1>
          <p className="page-desc">
            Выявленные повреждения инфраструктуры. Тяжесть (S1–S5) — масштаб повреждения; статус — ход работы; приоритет объекта считается отдельно.
          </p>
        </div>
      </div>

      <div className="filter-bar">
        <div className="chip-row" role="group" aria-label="Статус дефекта">
          <button className="chip" aria-pressed={status === ''} onClick={() => setParam('status', '')}>Все</button>
          {defectStatusOptions.map((s) => (
            <button key={s.value} className="chip" aria-pressed={status === s.value} onClick={() => setParam('status', s.value)}>
              {s.name}
            </button>
          ))}
        </div>
      </div>
      <div className="filter-bar">
        <select className="select" value={defectType} onChange={(e) => setParam('defect_type', e.target.value)} aria-label="Тип дефекта">
          <option value="">Все типы дефектов</option>
          {defectTypeOptions.map((t) => <option key={t.value} value={t.value}>{t.name}</option>)}
        </select>
        <select className="select" value={severityMin} onChange={(e) => setParam('severity_min', e.target.value)} aria-label="Минимальная тяжесть">
          <option value="">Любая тяжесть</option>
          <option value="3">S3 и выше</option>
          <option value="4">S4 и выше (критические)</option>
          <option value="5">Только S5</option>
        </select>
      </div>

      <div className="panel">
        {query.isPending && <LoadingState />}
        {query.error && <ErrorState error={query.error} onRetry={() => query.refetch()} />}
        {query.data && query.data.items.length === 0 && (
          <EmptyState title="Дефекты не найдены">
            Дефекты создаются автоматически при обнаружении повреждённых состояний и подтверждаются оператором.
          </EmptyState>
        )}
        {query.data && query.data.items.length > 0 && (
          <>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    <th>Дефект</th>
                    <th>Статус</th>
                    <th>Тяжесть</th>
                    <th>Наблюдений</th>
                    <th>Первое обнаружение</th>
                    <th>Последнее</th>
                  </tr>
                </thead>
                <tbody>
                  {query.data.items.map((d) => (
                    <tr key={d.id} className="clickable" tabIndex={0}
                      onClick={() => navigate(`/app/defects/${d.id}`)}
                      onKeyDown={(e) => { if (e.key === 'Enter') navigate(`/app/defects/${d.id}`); }}
                    >
                      <td>
                        <span className="cell-main">{label.defectType(d.defect_type)}</span>
                        <span className="cell-sub mono">{d.id.slice(0, 8)}</span>
                      </td>
                      <td><Status tone={defectStatusTone[d.status] ?? 'neutral'}>{label.defectStatus(d.status)}</Status></td>
                      <td><Severity value={d.severity} /></td>
                      <td className="num">{d.observation_count ?? '—'}</td>
                      <td className="muted">{fmtDateTime(d.first_detected_at)}</td>
                      <td className="muted">{fmtRelative(d.last_detected_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={query.data.page} pages={query.data.pages} total={query.data.total} pageSize={query.data.page_size}
              onPage={(p) => setParam('page', String(p))} noun={['дефект', 'дефекта', 'дефектов']} />
          </>
        )}
      </div>
    </div>
  );
}