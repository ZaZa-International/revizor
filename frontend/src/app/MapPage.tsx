import { useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  useAsset,
  useMapAssets,
  useMapDefects,
  useMapObservations,
  useMapRoutes,
} from '../data/hooks';
import { Badge, Button, ErrorState, KeyValue, LoadingState, Severity, Status } from '../components/ui';
import NetworkMap, { type LayerVisibility, type MapSelection } from '../components/map/NetworkMap';
import { BAND_COLORS } from '../components/map/MapView';
import { assetTypeIcon } from '../components/icons';
import { assetTypeOptions, bandTone, conditionTone, defectStatusTone, geoTone, label, priorityBandOptions } from '../lib/labels';
import { fmtCoord, fmtDateTime, fmtNumber, fmtRelative } from '../lib/format';
import { useDataSource } from '../data/source';

export default function MapPage() {
  const { isDemo } = useDataSource();
  const [params, setParams] = useSearchParams();
  const [visible, setVisible] = useState<LayerVisibility>({ assets: true, defects: true, observations: false, routes: true });
  const [assetType, setAssetType] = useState(params.get('asset_type') ?? '');
  const [band, setBand] = useState(params.get('priority_band') ?? '');
  const [defectStatus, setDefectStatus] = useState('');
  const [selection, setSelection] = useState<MapSelection | null>(null);

  const assetQuery = { asset_type: assetType || undefined, priority_band: band || undefined, limit: 2000 };
  const assets = useMapAssets(assetQuery);
  const defects = useMapDefects({ status: defectStatus || undefined, severity_min: params.get('severity_min') || undefined });
  const observations = useMapObservations({});
  const routes = useMapRoutes();

  const selectedAssetId = selection?.layer === 'assets' ? selection.id : null;
  const assetDetail = useAsset(selectedAssetId ?? undefined);

  const counts = useMemo(
    () => ({
      assets: assets.data?.features.length ?? 0,
      defects: defects.data?.features.length ?? 0,
      observations: observations.data?.features.length ?? 0,
      routes: routes.data?.features.length ?? 0,
    }),
    [assets.data, defects.data, observations.data, routes.data],
  );

  const toggle = (layer: keyof LayerVisibility) => setVisible((v) => ({ ...v, [layer]: !v[layer] }));

  const onSelect = (sel: MapSelection | null) => {
    setSelection(sel);
    const next = new URLSearchParams(params);
    if (sel) {
      next.set('selected', sel.id);
      next.set('layer', sel.layer);
    } else {
      next.delete('selected');
      next.delete('layer');
    }
    setParams(next, { replace: true });
  };

  const anyError = assets.error || defects.error || routes.error;
  const loading = assets.isPending || routes.isPending;

  const layerRows: { key: keyof LayerVisibility; name: string; color: string; count: number }[] = [
    { key: 'assets', name: 'Объекты (Asset)', color: 'var(--accent)', count: counts.assets },
    { key: 'defects', name: 'Дефекты', color: 'var(--crit)', count: counts.defects },
    { key: 'observations', name: 'Наблюдения', color: 'var(--warn)', count: counts.observations },
    { key: 'routes', name: 'Маршруты', color: 'var(--accent-dim)', count: counts.routes },
  ];

  return (
    <div>
      <div className="page-head" style={{ marginBottom: 'var(--sp-4)' }}>
        <div>
          <p className="eyebrow">Карта · {isDemo ? 'DEMO' : 'LIVE'}</p>
          <h1>Карта сети</h1>
        </div>
        <div className="page-head-actions">
          {anyError && (
            <Button size="sm" onClick={() => { void assets.refetch(); void defects.refetch(); void routes.refetch(); }}>
              Повторить загрузку
            </Button>
          )}
        </div>
      </div>

      {anyError && !loading && (
        <div style={{ marginBottom: 'var(--sp-4)' }}>
          <ErrorState error={anyError} onRetry={() => { void assets.refetch(); void defects.refetch(); }} />
        </div>
      )}

      <div className="map-workspace">
        <aside className="map-side" aria-label="Слои и фильтры">
          <div>
            <p className="eyebrow" style={{ marginBottom: 8 }}>Слои</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
              {layerRows.map((l) => (
                <button key={l.key} className="layer-toggle" aria-pressed={visible[l.key]} onClick={() => toggle(l.key)}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <i className="layer-dot" style={{ background: l.color }} />
                    {l.name}
                  </span>
                  <span className="layer-state">{visible[l.key] ? `${l.count} · вкл` : 'выкл'}</span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="eyebrow" style={{ marginBottom: 8 }}>Фильтры объектов</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <select className="select" value={assetType} onChange={(e) => setAssetType(e.target.value)} aria-label="Тип объекта">
                <option value="">Все типы</option>
                {assetTypeOptions.map((t) => (
                  <option key={t.value} value={t.value}>{t.name}</option>
                ))}
              </select>
              <select className="select" value={band} onChange={(e) => setBand(e.target.value)} aria-label="Приоритет">
                <option value="">Любой приоритет</option>
                {priorityBandOptions.map((b) => (
                  <option key={b.value} value={b.value}>{b.name}</option>
                ))}
              </select>
              <select className="select" value={defectStatus} onChange={(e) => setDefectStatus(e.target.value)} aria-label="Статус дефекта">
                <option value="">Дефекты: любой статус</option>
                <option value="OPEN">Открытые</option>
                <option value="CONFIRMED">Подтверждённые</option>
                <option value="IN_PROGRESS">В работе</option>
                <option value="RESOLVED">Устранённые</option>
              </select>
            </div>
          </div>

          <div>
            <p className="eyebrow" style={{ marginBottom: 8 }}>Легенда приоритета</p>
            <div className="legend" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 6 }}>
              {priorityBandOptions.map((b) => (
                <span key={b.value} className="legend-item">
                  <i className="legend-swatch" style={{ background: BAND_COLORS[b.value], borderRadius: '50%' }} />
                  {b.name}
                </span>
              ))}
              <span className="legend-item">
                <i className="legend-swatch" style={{ background: 'transparent', border: '2px solid var(--crit)', borderRadius: '50%' }} />
                кольцо — дефект S3+
              </span>
            </div>
          </div>

          <p className="faint" style={{ fontSize: 'var(--text-micro)' }}>
            Объекты без GPS в слои не попадают — они доступны в реестре. Координаты: [lon, lat], WGS84.
          </p>
        </aside>

        <div className="map-canvas">
          {loading ? (
            <LoadingState label="Загрузка геоданных…" />
          ) : (
            <NetworkMap
              assets={assets.data ?? null}
              defects={defects.data ?? null}
              observations={observations.data ?? null}
              routes={routes.data ?? null}
              visible={visible}
              selectedId={selection?.id ?? params.get('selected')}
              onSelect={onSelect}
            />
          )}
        </div>

        <aside className="map-context" aria-label="Выбранный объект" aria-live="polite">
          {!selection && (
            <div>
              <p className="eyebrow" style={{ marginBottom: 8 }}>Контекст</p>
              <p className="muted small">
                Выберите объект на карте, чтобы увидеть паспорт. Клик по кластеру приближает зону.
              </p>
              <hr className="divider" />
              <KeyValue
                items={[
                  ['Объектов в слое', <span className="num">{fmtNumber(counts.assets)}</span>],
                  ['Дефектов', <span className="num">{fmtNumber(counts.defects)}</span>],
                  ['Маршрутов', <span className="num">{fmtNumber(counts.routes)}</span>],
                ]}
              />
            </div>
          )}

          {selection?.layer === 'assets' && (
            <div>
              <p className="eyebrow" style={{ marginBottom: 8 }}>Объект</p>
              {assetDetail.isPending && <LoadingState />}
              {assetDetail.error && <ErrorState error={assetDetail.error} />}
              {assetDetail.data && (
                <AssetContext asset={assetDetail.data} />
              )}
              {!assetDetail.isPending && !assetDetail.data && !assetDetail.error && (
                <AssetContextFallback selection={selection} />
              )}
            </div>
          )}

          {selection?.layer === 'defects' && (
            <div>
              <p className="eyebrow" style={{ marginBottom: 8 }}>Дефект</p>
              <h2 className="panel-title" style={{ marginBottom: 12 }}>
                {label.defectType(String(selection.properties.defect_type ?? ''))}
              </h2>
              <KeyValue
                items={[
                  ['Статус', <Status tone={defectStatusTone[String(selection.properties.status)] ?? 'neutral'}>{label.defectStatus(String(selection.properties.status))}</Status>],
                  ['Тяжесть', <Severity value={Number(selection.properties.severity ?? 0)} />],
                  ['Объект', String(selection.properties.display_name ?? '—')],
                  ['Координаты', <span className="mono small">{fmtCoord(selection.lon, selection.lat)}</span>],
                ]}
              />
              <Link className="btn btn-primary btn-block" style={{ marginTop: 16 }} to={`/app/defects/${selection.id}`}>
                Карточка дефекта
              </Link>
            </div>
          )}

          {selection?.layer === 'observations' && (
            <div>
              <p className="eyebrow" style={{ marginBottom: 8 }}>Наблюдение</p>
              <KeyValue
                items={[
                  ['Тип', label.assetType(String(selection.properties.object_type ?? ''))],
                  ['Состояние', label.condition(String(selection.properties.condition_class ?? ''))],
                  ['Проверка', label.reviewStatus(String(selection.properties.review_status ?? ''))],
                  ['Дедупликация', label.dedup(String(selection.properties.dedup_result ?? ''))],
                  ['Время', fmtDateTime(String(selection.properties.observed_at ?? ''))],
                ]}
              />
              <Link className="btn btn-primary btn-block" style={{ marginTop: 16 }} to={`/app/observations/${selection.id}`}>
                Карточка наблюдения
              </Link>
            </div>
          )}

          {selection?.layer === 'routes' && (
            <div>
              <p className="eyebrow" style={{ marginBottom: 8 }}>Маршрут</p>
              <h2 className="panel-title" style={{ marginBottom: 12 }}>{String(selection.properties.name ?? 'Маршрут')}</h2>
              <Link className="btn btn-primary btn-block" to={`/app/routes/${selection.id}`}>
                Карточка маршрута
              </Link>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}

function AssetContext({ asset }: { asset: import('../api/types').Asset }) {
  const Icon = assetTypeIcon(asset.asset_type);
  return (
    <div>
      <div className="passport-title" style={{ marginBottom: 12 }}>
        <Icon />
        <h2 className="panel-title">{asset.display_name ?? asset.external_id ?? 'Объект'}</h2>
      </div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 }}>
        <Status tone={bandTone[asset.priority_band ?? ''] ?? 'neutral'}>{label.priorityBand(asset.priority_band)}</Status>
        <Badge>{label.assetType(asset.asset_type)}</Badge>
      </div>
      <KeyValue
        items={[
          ['Состояние', <Status tone={conditionTone(asset.current_condition)}>{label.condition(asset.current_condition)}</Status>],
          ['Тяжесть', <Severity value={asset.current_severity} />],
          ['Приоритет', <span className="num">{fmtNumber(asset.current_priority, 1)} / 100</span>],
          ['Геолокация', <Status tone={geoTone[asset.geolocation_status] ?? 'neutral'} shape="square">{label.geoStatus(asset.geolocation_status)}</Status>],
          ['Координаты', <span className="mono small">{fmtCoord(asset.longitude, asset.latitude)}</span>],
          ['Последний осмотр', fmtRelative(asset.last_observed_at)],
          ['Версия записи', <span className="num">{asset.version}</span>],
        ]}
      />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 16 }}>
        <Link className="btn btn-primary btn-block" to={`/app/assets/${asset.id}`}>
          Паспорт объекта
        </Link>
        <Link className="btn btn-block" to={`/app/observations?asset_id=${asset.id}`}>
          Наблюдения объекта
        </Link>
      </div>
    </div>
  );
}

function AssetContextFallback({ selection }: { selection: MapSelection }) {
  const p = selection.properties;
  return (
    <div>
      <h2 className="panel-title" style={{ marginBottom: 12 }}>{String(p.display_name ?? 'Объект')}</h2>
      <KeyValue
        items={[
          ['Тип', label.assetType(String(p.asset_type ?? ''))],
          ['Состояние', label.condition(String(p.current_condition ?? ''))],
          ['Приоритет', <span className="num">{fmtNumber(Number(p.current_priority ?? 0), 1)}</span>],
        ]}
      />
      <Link className="btn btn-primary btn-block" style={{ marginTop: 16 }} to={`/app/assets/${selection.id}`}>
        Паспорт объекта
      </Link>
    </div>
  );
}