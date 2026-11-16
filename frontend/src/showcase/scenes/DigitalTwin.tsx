import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '../../api/auth';
import { useDataSource } from '../../data/source';
import { useMapAssets, useMapDefects, useMapRoutes } from '../../data/hooks';
import { demoProvider } from '../../demo/provider';
import NetworkMap, { type LayerVisibility, type MapSelection } from '../../components/map/NetworkMap';
import { Badge, KeyValue, LoadingState, Severity, Status } from '../../components/ui';
import { assetTypeIcon } from '../../components/icons';
import { useNearViewport, useReveal } from '../motion';
import { bandTone, conditionTone, label } from '../../lib/labels';
import { fmtCoord, fmtNumber, fmtRelative } from '../../lib/format';

export default function DigitalTwin() {
  const { session } = useAuth();
  const { setMode } = useDataSource();
  const navigate = useNavigate();
  const live = !!session;
  const [visible, setVisible] = useState<LayerVisibility>({ assets: true, defects: true, observations: false, routes: true });
  const [selection, setSelection] = useState<MapSelection | null>(null);
  const [mountRef, near] = useNearViewport<HTMLDivElement>('500px');
  const headRef = useReveal<HTMLDivElement>();

  const liveAssets = useMapAssets({ limit: 1000 });
  const liveDefects = useMapDefects({});
  const liveRoutes = useMapRoutes();

  const demoAssets = useQuery({ queryKey: ['showcase-demo-assets'], queryFn: () => demoProvider.mapAssets({}), enabled: !live, staleTime: Infinity });
  const demoDefects = useQuery({ queryKey: ['showcase-demo-defects'], queryFn: () => demoProvider.mapDefects({}), enabled: !live, staleTime: Infinity });
  const demoRoutes = useQuery({ queryKey: ['showcase-demo-routes'], queryFn: () => demoProvider.mapRoutes(), enabled: !live, staleTime: Infinity });

  const assets = live ? liveAssets.data : demoAssets.data;
  const defects = live ? liveDefects.data : demoDefects.data;
  const routes = live ? liveRoutes.data : demoRoutes.data;
  const loading = live ? liveAssets.isPending : demoAssets.isPending;

  const openInPlatform = () => {
    if (!live) setMode('demo');
    if (selection?.layer === 'assets') navigate(`/app/assets/${selection.id}`);
    else if (selection?.layer === 'defects') navigate(`/app/defects/${selection.id}`);
    else navigate('/app/map');
  };

  const chips: { key: keyof LayerVisibility; name: string }[] = [
    { key: 'assets', name: 'Объекты' },
    { key: 'defects', name: 'Дефекты' },
    { key: 'routes', name: 'Маршруты' },
    { key: 'observations', name: 'Наблюдения' },
  ];

  return (
    <section className="sc-section" id="twin" aria-label="Интерактивная карта инфраструктуры">
      <div className="sc-section-head reveal" ref={headRef}>
        <p className="sc-eyebrow">The Digital Infrastructure</p>
        <h2>Сеть, с которой можно работать</h2>
        <p>
          Та же карта, что и в командном центре: слои объектов, дефектов и маршрутов,
          выбор объекта и паспорт. {live ? 'Показаны данные вашего API.' : 'Публичная демонстрация использует синтетический сценарий.'}
        </p>
      </div>

      <div className="twin-grid" ref={mountRef}>
        <div className="twin-map">
          {near ? (
            loading ? (
              <LoadingState label="Загрузка геоданных…" />
            ) : (
              <NetworkMap
                assets={assets ?? null}
                defects={defects ?? null}
                routes={routes ?? null}
                visible={visible}
                selectedId={selection?.id ?? null}
                onSelect={setSelection}
              />
            )
          ) : (
            <LoadingState label="Карта появится при прокрутке…" />
          )}
          <div style={{ position: 'absolute', top: 12, left: 12, zIndex: 5 }}>
            <Badge demo={!live}>{live ? 'ДАННЫЕ API' : 'ДЕМОНСТРАЦИОННЫЕ ДАННЫЕ'}</Badge>
          </div>
        </div>

        <div className="twin-side">
          <div className="twin-chips" role="group" aria-label="Слои карты">
            {chips.map((c) => (
              <button key={c.key} className="chip" aria-pressed={visible[c.key]} onClick={() => setVisible((v) => ({ ...v, [c.key]: !v[c.key] }))}>
                {c.name}
              </button>
            ))}
          </div>

          <div className="twin-object-card" aria-live="polite">
            {!selection && (
              <div>
                <p className="eyebrow" style={{ marginBottom: 10 }}>Выбранный объект</p>
                <p className="muted small">
                  Кликните по объекту на карте. Кластеры приближают зону, кольцо вокруг точки — дефект.
                  Объекты без GPS доступны в реестре платформы.
                </p>
                <hr className="divider" />
                <KeyValue
                  items={[
                    ['Объектов', <span className="num">{fmtNumber(assets?.features.length ?? 0)}</span>],
                    ['Дефектов', <span className="num">{fmtNumber(defects?.features.length ?? 0)}</span>],
                    ['Маршрутов', <span className="num">{fmtNumber(routes?.features.length ?? 0)}</span>],
                  ]}
                />
              </div>
            )}
            {selection && (
              <div>
                <p className="eyebrow" style={{ marginBottom: 10 }}>
                  {selection.layer === 'assets' ? 'Объект' : selection.layer === 'defects' ? 'Дефект' : selection.layer === 'routes' ? 'Маршрут' : 'Наблюдение'}
                </p>
                <SelectionCard selection={selection} />
                <button className="btn btn-primary btn-block" style={{ marginTop: 16 }} onClick={openInPlatform}>
                  Открыть в платформе →
                </button>
              </div>
            )}
          </div>

          <p className="faint" style={{ fontSize: 'var(--text-micro)' }}>
            Базовая карта: © Esri · HERE · Garmin · FAO · NOAA · USGS. При недоступности тайлов карта
            переходит в схематичный режим с координатной сеткой.
          </p>
        </div>
      </div>
    </section>
  );
}

function SelectionCard({ selection }: { selection: MapSelection }) {
  const p = selection.properties;
  const Icon = assetTypeIcon(String(p.asset_type ?? ''));
  if (selection.layer === 'assets') {
    return (
      <div>
        <div className="passport-title" style={{ marginBottom: 12 }}>
          <Icon />
          <h3 className="panel-title">{String(p.display_name ?? 'Объект')}</h3>
        </div>
        <KeyValue
          items={[
            ['Тип', label.assetType(String(p.asset_type ?? ''))],
            ['Состояние', <Status tone={conditionTone(String(p.current_condition ?? ''))}>{label.condition(String(p.current_condition ?? ''))}</Status>],
            ['Приоритет', <span className="num">{fmtNumber(Number(p.current_priority ?? 0), 0)} / 100</span>],
            ['Полоса', <Status tone={bandTone[String(p.priority_band ?? '')] ?? 'neutral'}>{label.priorityBand(String(p.priority_band ?? ''))}</Status>],
            ['Координаты', <span className="mono small">{fmtCoord(selection.lon, selection.lat)}</span>],
            ['Осмотр', fmtRelative(String(p.last_observed_at ?? ''))],
          ]}
        />
      </div>
    );
  }
  if (selection.layer === 'defects') {
    return (
      <KeyValue
        items={[
          ['Дефект', label.defectType(String(p.defect_type ?? ''))],
          ['Статус', label.defectStatus(String(p.status ?? ''))],
          ['Тяжесть', <Severity value={Number(p.severity ?? 0)} />],
          ['Координаты', <span className="mono small">{fmtCoord(selection.lon, selection.lat)}</span>],
        ]}
      />
    );
  }
  if (selection.layer === 'routes') {
    return (
      <KeyValue
        items={[
          ['Маршрут', String(p.name ?? '—')],
          ['Автомобиль', String(p.vehicle_id ?? '—')],
        ]}
      />
    );
  }
  return (
    <KeyValue
      items={[
        ['Тип', label.assetType(String(p.object_type ?? ''))],
        ['Состояние', label.condition(String(p.condition_class ?? ''))],
        ['Проверка', label.reviewStatus(String(p.review_status ?? ''))],
      ]}
    />
  );
}