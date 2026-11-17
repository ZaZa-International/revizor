import { useNavigate } from 'react-router-dom';
import { useDataSource } from '../../data/source';
import { Badge, LoadingState, Status } from '../../components/ui';
import NetworkMap from '../../components/map/NetworkMap';
import { IconArrowRight, IconCheck, IconClose } from '../../components/icons';
import { useNearViewport, useReveal } from '../motion';
import { useShowcaseData } from '../useShowcaseData';
import { fmtNumber, fmtPercent } from '../../lib/format';

export default function PlatformPreview() {
  const headRef = useReveal<HTMLDivElement>();
  const [mountRef, near] = useNearViewport<HTMLDivElement>('400px');
  const { live, overview, assets, routes, queueTotal, loading } = useShowcaseData();
  const { setMode } = useDataSource();
  const navigate = useNavigate();

  const enter = (path: string) => {
    if (!live) setMode('demo');
    navigate(path);
  };

  return (
    <section className="sc-section" id="platform" aria-label="Командный центр">
      <div className="sc-section-head reveal" ref={headRef}>
        <p className="sc-eyebrow">Command Center</p>
        <h2>Рабочая среда, а не декорация</h2>
        <p>
          Ниже — живые компоненты платформы на {live ? 'данных вашего API' : 'демо-сценарии'}.
          Полная версия: реестры, карта, очередь проверки, задачи обработки, аналитика и выгрузки.
        </p>
      </div>

      <div className="preview-grid" ref={mountRef}>
        <div className="preview-card">
          <div className="preview-card-head">
            <span className="eyebrow">/app · Обзор</span>
          </div>
          <div className="preview-card-body">
            {loading || !overview ? (
              <LoadingState />
            ) : (
              <>
                <div className="preview-kpis">
                  <div className="preview-kpi">
                    <div className="v">{fmtNumber(overview.assets_total)}</div>
                    <div className="l">объектов</div>
                  </div>
                  <div className="preview-kpi">
                    <div className="v">{fmtNumber(overview.observations_total)}</div>
                    <div className="l">наблюдений</div>
                  </div>
                  <div className="preview-kpi">
                    <div className="v" style={{ color: 'var(--crit)' }}>{fmtNumber(overview.defects_total)}</div>
                    <div className="l">дефектов</div>
                  </div>
                  <div className="preview-kpi">
                    <div className="v" style={{ color: 'var(--warn)' }}>{fmtNumber(queueTotal)}</div>
                    <div className="l">в очереди</div>
                  </div>
                </div>
                <p className="faint small" style={{ marginTop: 'var(--sp-4)' }}>
                  Проверено наблюдений: {fmtPercent(overview.observations_reviewed_ratio, 0)}.
                  Сводка обновляется из агрегатов API.
                </p>
              </>
            )}
          </div>
          <div className="preview-card-foot">
            <button className="link small" onClick={() => enter('/app')}>
              Открыть обзор <IconArrowRight className="icon-sm" style={{ display: 'inline', verticalAlign: '-2px' }} />
            </button>
          </div>
        </div>

        <div className="preview-card">
          <div className="preview-card-head">
            <span className="eyebrow">/app/map · Карта</span>
          </div>
          <div className="preview-card-body">
            <div className="preview-map">
              {near ? (
                <NetworkMap
                  assets={assets ?? null}
                  routes={routes ?? null}
                  visible={{ assets: true, defects: false, observations: false, routes: true }}
                />
              ) : (
                <LoadingState label="Карта…" />
              )}
            </div>
            <p className="faint small" style={{ marginTop: 'var(--sp-3)' }}>
              Слои Asset / Defects / Observations / Routes, кластеризация, паспорт по клику.
            </p>
          </div>
          <div className="preview-card-foot">
            <button className="link small" onClick={() => enter('/app/map')}>
              Открыть карту <IconArrowRight className="icon-sm" style={{ display: 'inline', verticalAlign: '-2px' }} />
            </button>
          </div>
        </div>

        <div className="preview-card">
          <div className="preview-card-head">
            <span className="eyebrow">/app/reviews · Проверка</span>
          </div>
          <div className="preview-card-body">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 'var(--sp-4)' }}>
              <span className="small muted">Очередь UNREVIEWED</span>
              <Status tone={queueTotal > 0 ? 'warn' : 'ok'}>{fmtNumber(queueTotal)}</Status>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <span className="decision-btn" style={{ cursor: 'default' }}>
                <span className="decision-name"><IconCheck className="icon-sm" style={{ display: 'inline', verticalAlign: '-2px', marginRight: 4, color: 'var(--ok)' }} />Подтвердить</span>
                <span className="decision-hint">предсказание верно</span>
              </span>
              <span className="decision-btn" style={{ cursor: 'default' }}>
                <span className="decision-name"><IconClose className="icon-sm" style={{ display: 'inline', verticalAlign: '-2px', marginRight: 4, color: 'var(--crit)' }} />Отклонить / скорректировать</span>
                <span className="decision-hint">с исправлением типа, состояния, тяжести</span>
              </span>
            </div>
            <p className="faint small" style={{ marginTop: 'var(--sp-4)' }}>
              Решения append-only; исходное предсказание ML сохраняется.
            </p>
          </div>
          <div className="preview-card-foot">
            <button className="link small" onClick={() => enter('/app/reviews')}>
              Открыть проверку <IconArrowRight className="icon-sm" style={{ display: 'inline', verticalAlign: '-2px' }} />
            </button>
          </div>
        </div>
      </div>

      <div style={{ marginTop: 'var(--sp-5)', display: 'flex', gap: 'var(--sp-3)', alignItems: 'center', flexWrap: 'wrap' }}>
        <Badge demo={!live}>{live ? 'ДАННЫЕ API' : 'DEMO-ДАННЫЕ'}</Badge>
        <span className="faint small">
          Десять разделов: Overview · Map · Assets · Observations · Defects · Reviews · Jobs · Routes · Analytics · Exports
        </span>
      </div>
    </section>
  );
}