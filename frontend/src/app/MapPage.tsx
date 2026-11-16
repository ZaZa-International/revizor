import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Map as MLMap } from 'maplibre-gl';
import {
  useCoverage,
  useMapAssets,
  useMapDefects,
  useMapObservations,
  useMapRoutes,
} from '../data/hooks';
import { Badge, Button, ErrorState, KeyValue, LoadingState, toast } from '../components/ui';
import NetworkMap, { type MapSelection, type MapStats } from '../components/map/NetworkMap';
import DeckOverlay from '../components/map/DeckOverlay';
import {
  AssetInspection,
  DefectInspection,
  ObservationInspection,
  RouteInspection,
  type InspectionTab,
  type SelectionNav,
} from '../components/map/inspection';
import { BAND_COLORS, GEO_COLORS } from '../geo/palette';
import { adaptCollection } from '../geo/adapter';
import { coverageAreaOutline, coverageCells } from '../geo/coverage';
import { useMapState } from '../geo/state';
import type { MapCamera, MapMode } from '../geo/types';
import { assetTypeOptions, defectStatusOptions, priorityBandOptions } from '../lib/labels';
import { fmtNumber, fmtPercent } from '../lib/format';
import { useDataSource } from '../data/source';
import { findWalkthroughTarget, useWalkthrough, WalkthroughPanel } from '../demo/walkthrough';

const DEFAULT_CAMERA: MapCamera = { center: [37.6173, 55.7558], zoom: 12, pitch: 0, bearing: 0 };

export default function MapPage() {
  const { isDemo } = useDataSource();
  const mapApi = useMapState();
  const { state } = mapApi;
  const [params] = useState(() => new URLSearchParams(window.location.search));
  const statsEnabled = params.get('stats') === '1';

  const [bbox, setBbox] = useState<string | null>(null);
  const [tab, setTab] = useState<InspectionTab>('overview');
  const [mapInstance, setMapInstance] = useState<MLMap | null>(null);
  const [stats, setStats] = useState<MapStats | null>(null);
  const [fitSignal, setFitSignal] = useState(0);
  const lastCameraRef = useRef<MapCamera | null>(null);

  const walkthroughTarget = useMemo(() => (isDemo ? findWalkthroughTarget() : null), [isDemo]);
  const wt = useWalkthrough({ mapApi, setTab }, walkthroughTarget);

  const obsEnabled = state.layers.observations || state.layers.heatmap;
  const assets = useMapAssets({
    asset_type: state.filters.asset_type || undefined,
    priority_band: state.filters.priority_band || undefined,
    bbox: bbox ?? undefined,
    limit: 2000,
  });
  const defects = useMapDefects({
    status: state.filters.defect_status || undefined,
    severity_min: state.filters.severity_min || undefined,
    bbox: bbox ?? undefined,
    limit: 2000,
  });
  const observations = useMapObservations(
    {
      bbox: bbox ?? undefined,
      date_from: state.timeRange.from || undefined,
      date_to: state.timeRange.to ? `${state.timeRange.to}T23:59:59Z` : undefined,
      limit: 2000,
    },
    { enabled: obsEnabled },
  );
  const routes = useMapRoutes();
  const coverage = useCoverage({ enabled: state.layers.coverage });

  const adaptedDefects = useMemo(() => adaptCollection('defects', defects.data), [defects.data]);
  const coverageRender = useMemo(
    () => (state.layers.coverage ? coverageCells(coverage.data) : null),
    [state.layers.coverage, coverage.data],
  );
  const coverageOutline = useMemo(
    () => (state.layers.coverage ? coverageAreaOutline(coverage.data) : null),
    [state.layers.coverage, coverage.data],
  );

  const counts = {
    assets: assets.data?.features.length ?? 0,
    defects: defects.data?.features.length ?? 0,
    observations: observations.data?.features.length ?? 0,
    routes: routes.data?.features.length ?? 0,
  };

  const onViewportChange = useCallback((b: string) => {
    setBbox((prev) => (prev === b ? prev : b));
  }, []);

  const onCameraChange = useCallback(
    (cam: MapCamera) => {
      lastCameraRef.current = cam;
      mapApi.setCamera(cam);
    },
    [mapApi],
  );

  const flyTo = useCallback(
    (lon: number, lat: number) => {
      const base = lastCameraRef.current ?? state.camera ?? DEFAULT_CAMERA;
      mapApi.setCamera({ ...base, center: [lon, lat], zoom: Math.max(base.zoom, 15.5) });
    },
    [mapApi, state.camera],
  );

  const onSelect = useCallback(
    (sel: MapSelection | null) => {
      if (!sel) {
        mapApi.select(null);
        return;
      }
      mapApi.select({ layer: sel.layer, id: sel.id });
      setTab('overview');
      flyTo(sel.lon, sel.lat);
    },
    [mapApi, flyTo],
  );

  const onNavigate = useCallback(
    (sel: SelectionNav) => {
      mapApi.select(sel);
      setTab('overview');
    },
    [mapApi],
  );

  const setMode = useCallback(
    (m: MapMode) => {
      const base = lastCameraRef.current ?? state.camera ?? DEFAULT_CAMERA;
      mapApi.update({
        mode: m,
        camera: { ...base, pitch: m === '3d' ? 55 : 0, bearing: m === '3d' ? base.bearing || -15 : 0 },
      });
    },
    [mapApi, state.camera],
  );

  const resetCamera = useCallback(() => {
    setFitSignal((n) => n + 1);
  }, []);

  const anyError = assets.error || defects.error || routes.error || (obsEnabled && observations.error);
  const loading = (assets.isPending && !assets.data) || (routes.isPending && !routes.data);
  const selection = state.selection;

  const layerRows: { key: keyof typeof state.layers; name: string; color: string; count: number | null }[] = [
    { key: 'assets', name: 'Объекты (Asset)', color: 'var(--accent)', count: counts.assets },
    { key: 'defects', name: 'Дефекты', color: 'var(--crit)', count: counts.defects },
    { key: 'observations', name: 'Наблюдения', color: 'var(--warn)', count: obsEnabled ? counts.observations : null },
    { key: 'routes', name: 'Маршруты', color: 'var(--accent-dim)', count: counts.routes },
    { key: 'coverage', name: 'Покрытие', color: 'var(--ok)', count: coverage.data?.covered_cells ?? null },
    { key: 'heatmap', name: 'Плотность наблюдений', color: 'var(--warn)', count: null },
    { key: 'hexbin', name: 'Гексагоны дефектов', color: 'var(--crit)', count: null },
  ];

  return (
    <div>
      <div className="page-head" style={{ marginBottom: 'var(--sp-4)' }}>
        <div>
          <p className="eyebrow">Карта · {isDemo ? 'DEMO' : 'LIVE'} · {state.mode === '3d' ? '3D CITY' : '2D'}</p>
          <h1>Карта сети</h1>
        </div>
        <div className="page-head-actions">
          {anyError && (
            <Button size="sm" onClick={() => { void assets.refetch(); void defects.refetch(); void routes.refetch(); void observations.refetch(); }}>
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
                <button key={l.key} className="layer-toggle" aria-pressed={state.layers[l.key]} onClick={() => mapApi.toggleLayer(l.key)}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <i className="layer-dot" style={{ background: l.color }} />
                    {l.name}
                  </span>
                  <span className="layer-state">
                    {state.layers[l.key] ? (l.count != null ? `${l.count} · вкл` : 'вкл') : 'выкл'}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <p className="eyebrow" style={{ marginBottom: 8 }}>Фильтры</p>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <select className="select" value={state.filters.asset_type} onChange={(e) => mapApi.setFilter('asset_type', e.target.value)} aria-label="Тип объекта">
                <option value="">Все типы</option>
                {assetTypeOptions.map((t) => (
                  <option key={t.value} value={t.value}>{t.name}</option>
                ))}
              </select>
              <select className="select" value={state.filters.priority_band} onChange={(e) => mapApi.setFilter('priority_band', e.target.value)} aria-label="Приоритет">
                <option value="">Любой приоритет</option>
                {priorityBandOptions.map((b) => (
                  <option key={b.value} value={b.value}>{b.name}</option>
                ))}
              </select>
              <select className="select" value={state.filters.defect_status} onChange={(e) => mapApi.setFilter('defect_status', e.target.value)} aria-label="Статус дефекта">
                <option value="">Дефекты: любой статус</option>
                {defectStatusOptions.map((s) => (
                  <option key={s.value} value={s.value}>{s.name}</option>
                ))}
              </select>
              <select className="select" value={state.filters.severity_min} onChange={(e) => mapApi.setFilter('severity_min', e.target.value)} aria-label="Минимальная тяжесть">
                <option value="">Любая тяжесть</option>
                {[1, 2, 3, 4, 5].map((s) => (
                  <option key={s} value={String(s)}>S{s}+</option>
                ))}
              </select>
            </div>
          </div>

          {(state.view === 'infrastructure' || state.layers.observations) && (
            <div>
              <p className="eyebrow" style={{ marginBottom: 8 }}>Период наблюдений</p>
              <div className="time-range">
                <input
                  className="input"
                  type="date"
                  value={state.timeRange.from}
                  onChange={(e) => mapApi.setTimeRange(e.target.value, state.timeRange.to)}
                  aria-label="Дата начала периода"
                />
                <input
                  className="input"
                  type="date"
                  value={state.timeRange.to}
                  onChange={(e) => mapApi.setTimeRange(state.timeRange.from, e.target.value)}
                  aria-label="Дата конца периода"
                />
                {(state.timeRange.from || state.timeRange.to) && (
                  <Button size="sm" variant="ghost" onClick={() => mapApi.setTimeRange('', '')}>
                    Сбросить период
                  </Button>
                )}
              </div>
            </div>
          )}

          {state.layers.coverage && coverage.data && (
            <div>
              <p className="eyebrow" style={{ marginBottom: 8 }}>Покрытие обследованием</p>
              <KeyValue
                items={[
                  ['Покрытие зоны', <span className="num">{fmtPercent(coverage.data.coverage_ratio)}</span>],
                  ['Ячейки с данными', <span className="num">{fmtNumber(coverage.data.covered_cells)} / {fmtNumber(coverage.data.total_cells)}</span>],
                  ['Пробелы', <span className="num">{fmtNumber(coverage.data.gap_cells)}</span>],
                ]}
              />
              <p className="faint" style={{ fontSize: 'var(--text-micro)', marginTop: 6 }}>
                Сетка {coverage.data.grid_cell_m} м по данным /analytics/coverage.
              </p>
            </div>
          )}

          <div>
            <p className="eyebrow" style={{ marginBottom: 8 }}>Легенда</p>
            <div className="legend" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: 6 }}>
              {priorityBandOptions.map((b) => (
                <span key={b.value} className="legend-item">
                  <i className="legend-swatch" style={{ background: BAND_COLORS[b.value], borderRadius: '50%' }} />
                  {b.name}
                </span>
              ))}
              <span className="legend-item">
                <i className="legend-swatch" style={{ background: 'transparent', border: `2px solid ${GEO_COLORS.crit}`, borderRadius: '50%' }} />
                кольцо — дефект S4+
              </span>
              <span className="legend-item">
                <i className="legend-swatch" style={{ background: 'transparent', border: `2px solid ${GEO_COLORS.warn}`, borderRadius: '50%' }} />
                кольцо — дефект S1–3
              </span>
              <span className="legend-item">
                <i className="legend-swatch" style={{ background: GEO_COLORS.warn, borderRadius: '50%' }} />
                наблюдение без проверки
              </span>
              <span className="legend-item">
                <i className="legend-swatch" style={{ background: 'transparent', border: `1px dashed ${GEO_COLORS.accent}`, borderRadius: '50%' }} />
                неопределённость GPS (ESTIMATED)
              </span>
            </div>
          </div>

          <p className="faint" style={{ fontSize: 'var(--text-micro)' }}>
            Объекты без GPS в слои не попадают — они доступны в реестре. Координаты: [lon, lat], WGS84.
            Высоты зданий: OSM (render_height), могут быть оценкой по этажам.
          </p>
        </aside>

        <div className="map-canvas">
          {loading ? (
            <LoadingState label="Загрузка геоданных…" />
          ) : (
            <>
              <div className="map-toolbar" role="toolbar" aria-label="Управление картой">
                <div className="segmented" role="group" aria-label="Режим карты">
                  <button className={state.mode === '2d' ? 'on' : ''} aria-pressed={state.mode === '2d'} onClick={() => setMode('2d')}>2D</button>
                  <button className={state.mode === '3d' ? 'on' : ''} aria-pressed={state.mode === '3d'} onClick={() => setMode('3d')}>3D</button>
                </div>
                <select
                  className="select select-sm"
                  value={state.view}
                  onChange={(e) => mapApi.setView(e.target.value as 'network' | 'infrastructure')}
                  aria-label="Режим отображения"
                >
                  <option value="network">Сеть</option>
                  <option value="infrastructure">Инфраструктура</option>
                </select>
                <Button size="sm" variant="ghost" onClick={resetCamera} aria-label="Сбросить камеру" title="Сбросить камеру">
                  ⌂
                </Button>
                {isDemo && walkthroughTarget && !wt.active && (
                  <Button size="sm" onClick={wt.start}>
                    Демо-сценарий
                  </Button>
                )}
              </div>
              <NetworkMap
                assets={assets.data ?? null}
                defects={defects.data ?? null}
                observations={observations.data ?? null}
                routes={routes.data ?? null}
                visible={{
                  assets: state.layers.assets,
                  defects: state.layers.defects,
                  observations: state.layers.observations,
                  routes: state.layers.routes,
                }}
                selectedId={selection?.id ?? null}
                onSelect={onSelect}
                mode={state.mode}
                camera={state.camera}
                onCameraChange={onCameraChange}
                onViewportChange={onViewportChange}
                coverage={coverageRender}
                coverageOutline={coverageOutline}
                showCoverage={state.layers.coverage}
                showHeatmap={state.layers.heatmap}
                showAccuracy={state.view === 'infrastructure'}
                fitSignal={fitSignal}
                onMapReady={setMapInstance}
                onStats={statsEnabled ? setStats : undefined}
              />
              <DeckOverlay
                map={mapInstance}
                enabled={state.layers.hexbin}
                defects={adaptedDefects.features}
                mode={state.mode}
                onUnavailable={() => toast('info', 'Гексагональная агрегация требует WebGL2')}
              />
              <WalkthroughPanel wt={wt} />
              {statsEnabled && <MapStatsPanel stats={stats} />}
            </>
          )}
        </div>

        <aside className="map-context" aria-label="Выбранный объект" aria-live="polite">
          {!selection && (
            <div>
              <p className="eyebrow" style={{ marginBottom: 8 }}>Контекст</p>
              <p className="muted small">
                Выберите объект на карте, чтобы увидеть паспорт, наблюдения, дефекты и историю
                состояния. Клик по кластеру приближает зону.
              </p>
              <hr className="divider" />
              <KeyValue
                items={[
                  ['Объектов в слое', <span className="num">{fmtNumber(counts.assets)}</span>],
                  ['Дефектов', <span className="num">{fmtNumber(counts.defects)}</span>],
                  ['Наблюдений', <span className="num">{obsEnabled ? fmtNumber(counts.observations) : '—'}</span>],
                  ['Маршрутов', <span className="num">{fmtNumber(counts.routes)}</span>],
                ]}
              />
              {isDemo && walkthroughTarget && !wt.active && (
                <Button block style={{ marginTop: 16 }} onClick={wt.start}>
                  Запустить демо-сценарий
                </Button>
              )}
            </div>
          )}

          {selection?.layer === 'assets' && (
            <AssetInspection assetId={selection.id} tab={tab} onTab={setTab} onNavigate={onNavigate} />
          )}
          {selection?.layer === 'observations' && (
            <ObservationInspection observationId={selection.id} onNavigate={onNavigate} onConfirmed={wt.notifyConfirmed} />
          )}
          {selection?.layer === 'defects' && (
            <DefectInspection defectId={selection.id} onNavigate={onNavigate} />
          )}
          {selection?.layer === 'routes' && <RouteInspection routeId={selection.id} />}
        </aside>
      </div>
    </div>
  );
}

function MapStatsPanel({ stats }: { stats: MapStats | null }) {
  const [fps, setFps] = useState(0);
  useEffect(() => {
    let frames = 0;
    let last = performance.now();
    let raf = 0;
    const loop = (t: number) => {
      frames++;
      if (t - last >= 1000) {
        setFps(Math.round((frames * 1000) / (t - last)));
        frames = 0;
        last = t;
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);
  const memory = (performance as unknown as { memory?: { usedJSHeapSize: number } }).memory;
  return (
    <div className="map-stats" role="status" aria-label="Статистика карты">
      <Badge>PERF</Badge>
      <span className="num">{fps} fps</span>
      <span className="num">{stats?.features ?? 0} features</span>
      <span className="num">{stats?.layers ?? 0} layers</span>
      {stats?.rejected ? <span className="num">rejected: {stats.rejected}</span> : null}
      {memory && <span className="num">{Math.round(memory.usedJSHeapSize / 1048576)} MB</span>}
    </div>
  );
}
