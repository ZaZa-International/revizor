import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAssets } from '../data/hooks';
import { Badge, EmptyState, ErrorState, LoadingState, Pagination, SearchInput, Severity, Status } from '../components/ui';
import { assetTypeIcon } from '../components/icons';
import { assetTypeOptions, bandTone, conditionTone, geoTone, label, lifecycleOptions, priorityBandOptions } from '../lib/labels';
import { fmtNumber, fmtRelative } from '../lib/format';

const SORTABLE = ['current_priority', 'current_severity', 'last_observed_at', 'asset_type', 'created_at'];

export default function AssetsPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();

  const page = Number(params.get('page') ?? 1);
  const search = params.get('search') ?? '';
  const assetType = params.get('asset_type') ?? '';
  const band = params.get('priority_band') ?? '';
  const lifecycle = params.get('lifecycle_status') ?? '';
  const geo = params.get('geolocation_status') ?? '';
  const sortBy = params.get('sort_by') ?? 'created_at';
  const order = params.get('order') ?? 'desc';

  const query = useAssets({
    page,
    page_size: 20,
    search: search || undefined,
    asset_type: assetType || undefined,
    priority_band: band || undefined,
    lifecycle_status: lifecycle || undefined,
    geolocation_status: geo || undefined,
    sort_by: sortBy,
    order,
  });

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== 'page') next.delete('page');
    setParams(next, { replace: true });
  };

  const toggleSort = (field: string) => {
    if (!SORTABLE.includes(field)) return;
    const next = new URLSearchParams(params);
    if (sortBy === field) next.set('order', order === 'desc' ? 'asc' : 'desc');
    else {
      next.set('sort_by', field);
      next.set('order', 'desc');
    }
    setParams(next, { replace: true });
  };

  const th = (field: string, title: string) => (
    <th
      className={SORTABLE.includes(field) ? 'sortable' : undefined}
      onClick={() => toggleSort(field)}
      aria-sort={sortBy === field ? (order === 'desc' ? 'descending' : 'ascending') : undefined}
    >
      {title}
      {sortBy === field && <span className="sort-arrow">{order === 'desc' ? '↓' : '↑'}</span>}
    </th>
  );

  return (
    <div className="assets-page">
      <div className="page-head">
        <div>
          <p className="eyebrow">Реестр</p>
          <h1>Объекты инфраструктуры</h1>
          <p className="page-desc">
            Физические объекты сети: колодцы, опоры, шкафы, кабельные линии. Паспорт хранит текущее состояние и историю изменений.
          </p>
        </div>
      </div>

      <div className="filter-bar">
        <SearchInput value={search} onChange={(v) => setParam('search', v)} placeholder="Название, external ID…" ariaLabel="Поиск объектов" />
        <select className="select" value={assetType} onChange={(e) => setParam('asset_type', e.target.value)} aria-label="Тип объекта">
          <option value="">Все типы</option>
          {assetTypeOptions.map((t) => <option key={t.value} value={t.value}>{t.name}</option>)}
        </select>
        <select className="select" value={band} onChange={(e) => setParam('priority_band', e.target.value)} aria-label="Приоритет">
          <option value="">Любой приоритет</option>
          {priorityBandOptions.map((b) => <option key={b.value} value={b.value}>{b.name}</option>)}
        </select>
        <select className="select" value={lifecycle} onChange={(e) => setParam('lifecycle_status', e.target.value)} aria-label="Жизненный цикл">
          <option value="">Любой статус</option>
          {lifecycleOptions.map((l) => <option key={l.value} value={l.value}>{l.name}</option>)}
        </select>
        <select className="select" value={geo} onChange={(e) => setParam('geolocation_status', e.target.value)} aria-label="Геолокация">
          <option value="">Любая геолокация</option>
          <option value="CONFIRMED">Подтверждена</option>
          <option value="ESTIMATED">Оценочная</option>
          <option value="UNAVAILABLE">Нет GPS</option>
        </select>
      </div>

      <div className="panel">
        {query.isPending && <LoadingState />}
        {query.error && <ErrorState error={query.error} onRetry={() => query.refetch()} />}
        {query.data && query.data.items.length === 0 && (
          <EmptyState title="Объекты не найдены">
            Измените фильтры или загрузите материалы обследования — объекты появятся после обработки и дедупликации.
          </EmptyState>
        )}
        {query.data && query.data.items.length > 0 && (
          <>
            <div className="table-wrap">
              <table className="table">
                <thead>
                  <tr>
                    {th('asset_type', 'Объект')}
                    <th>Состояние</th>
                    {th('current_severity', 'Тяжесть')}
                    {th('current_priority', 'Приоритет')}
                    <th>Геолокация</th>
                    {th('last_observed_at', 'Осмотр')}
                  </tr>
                </thead>
                <tbody>
                  {query.data.items.map((a) => {
                    const Icon = assetTypeIcon(a.asset_type);
                    return (
                      <tr
                        key={a.id}
                        className="clickable"
                        tabIndex={0}
                        onClick={() => navigate(`/app/assets/${a.id}`)}
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') navigate(`/app/assets/${a.id}`);
                        }}
                      >
                        <td>
                          <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                            <Icon style={{ color: 'var(--muted)' }} />
                            <span>
                              <span className="cell-main">{a.display_name ?? a.external_id ?? a.id.slice(0, 8)}</span>
                              <span className="cell-sub mono">{a.external_id ?? a.id.slice(0, 8)} · {label.assetTypeShort(a.asset_type)}</span>
                            </span>
                          </span>
                        </td>
                        <td>
                          <Status tone={conditionTone(a.current_condition)}>{label.condition(a.current_condition)}</Status>
                        </td>
                        <td><Severity value={a.current_severity} /></td>
                        <td>
                          <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                            <span className="num">{fmtNumber(a.current_priority, 0)}</span>
                            <Badge tone={bandTone[a.priority_band ?? ''] === 'crit' ? 'crit' : bandTone[a.priority_band ?? ''] === 'warn' ? 'warn' : undefined}>
                              {label.priorityBand(a.priority_band).replace(' приоритет', '')}
                            </Badge>
                          </span>
                        </td>
                        <td>
                          <Status tone={geoTone[a.geolocation_status] ?? 'neutral'} shape="square">
                            {label.geoStatus(a.geolocation_status)}
                          </Status>
                        </td>
                        <td className="muted">{fmtRelative(a.last_observed_at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <div className="assets-cards">
              {query.data.items.map((a) => {
                const Icon = assetTypeIcon(a.asset_type);
                return (
                  <button
                    key={a.id}
                    type="button"
                    className="asset-card"
                    onClick={() => navigate(`/app/assets/${a.id}`)}
                  >
                    <span className="asset-card-head">
                      <Icon style={{ color: 'var(--muted)' }} />
                      <span className="asset-card-titles">
                        <span className="asset-card-name">{a.display_name ?? a.external_id ?? a.id.slice(0, 8)}</span>
                        <span className="asset-card-id mono">{a.external_id ?? a.id.slice(0, 8)} · {label.assetTypeShort(a.asset_type)}</span>
                      </span>
                      <span className="num asset-card-priority" title="Текущий приоритет">{fmtNumber(a.current_priority, 0)}</span>
                    </span>
                    <span className="asset-card-meta">
                      <Status tone={conditionTone(a.current_condition)}>{label.condition(a.current_condition)}</Status>
                      <Severity value={a.current_severity} />
                      <Badge tone={bandTone[a.priority_band ?? ''] === 'crit' ? 'crit' : bandTone[a.priority_band ?? ''] === 'warn' ? 'warn' : undefined}>
                        {label.priorityBand(a.priority_band).replace(' приоритет', '')}
                      </Badge>
                      <Status tone={geoTone[a.geolocation_status] ?? 'neutral'} shape="square">
                        {label.geoStatus(a.geolocation_status)}
                      </Status>
                    </span>
                    <span className="asset-card-foot muted">Осмотр: {fmtRelative(a.last_observed_at)}</span>
                  </button>
                );
              })}
            </div>
            <Pagination
              page={query.data.page}
              pages={query.data.pages}
              total={query.data.total}
              pageSize={query.data.page_size}
              onPage={(p) => setParam('page', String(p))}
              noun={['объект', 'объекта', 'объектов']}
            />
          </>
        )}
      </div>
    </div>
  );
}