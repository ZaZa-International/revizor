import { useMemo, useState } from 'react';
import { demoData } from '../../demo/data';
import { demoFrameSvg } from '../../demo/frames';
import { Badge, Button, KeyValue, Severity, Status } from '../../components/ui';
import { IconArrowRight, IconCheck, IconChevronLeft, IconClose } from '../../components/icons';
import { useReveal } from '../motion';
import { conditionTone, label } from '../../lib/labels';
import { fmtCoord, fmtDateTime, fmtNumber, fmtPercent } from '../../lib/format';

/* Визуалы сценария — HTML на данных демо-датасета (не захардкоженные SVG). */

function DedupVisual({ obs, asset }: { obs: (typeof demoData.observations)[number]; asset?: (typeof demoData.assets)[number] }) {
  const e = (obs.dedup_explanation ?? {}) as Record<string, unknown>;
  return (
    <div style={{ padding: 'var(--sp-6)' }} role="img" aria-label="Сопоставление обнаружения с существующим объектом">
      <div className="scenario-dedup">
        <div className="scenario-dedup-node">
          <span className="eyebrow">detection</span>
          <span className="mono small">{fmtCoord(obs.longitude, obs.latitude)}</span>
          <span className="muted small">{label.assetType(obs.object_type)} · {fmtPercent(obs.detector_confidence, 0)}</span>
        </div>
        <div className="scenario-dedup-link">
          <span className="num small">Δ {fmtNumber(Number(e.distance_m ?? 0), 1)} м</span>
          <span className="faint" style={{ fontSize: 'var(--text-micro)' }}>тип: совпадает</span>
        </div>
        <div className="scenario-dedup-node">
          <span className="eyebrow">asset</span>
          <span className="mono small">{fmtCoord(asset?.longitude, asset?.latitude)}</span>
          <span className="muted small">{asset?.display_name ?? '—'}</span>
        </div>
      </div>
      <div className="spec-row" style={{ justifyContent: 'center', marginTop: 'var(--sp-4)' }}>
        <span className="num small">score {fmtNumber(obs.dedup_score ?? 0, 2)}</span>
        <Status tone="ok" shape="square">matched</Status>
        <span className="muted small">объект не дублируется</span>
      </div>
    </div>
  );
}

function HistoryVisual({ assetId, confirmed }: { assetId?: string | null; confirmed: boolean | null }) {
  const entries = demoData.history
    .filter((h) => h.asset_id === assetId)
    .sort((a, b) => (a.detected_at ?? '').localeCompare(b.detected_at ?? ''));
  return (
    <div style={{ padding: 'var(--sp-6)' }} role="img" aria-label="История состояния объекта">
      <div className="spec-timeline">
        {entries.map((h) => (
          <div className="spec-timeline-item" key={h.id}>
            <i className={`spec-dot tone-${conditionTone(h.new_condition)}`} aria-hidden />
            <div>
              <div className="spec-row" style={{ padding: 0 }}>
                <span className="mono small">{fmtDateTime(h.detected_at)}</span>
                <span className="muted small">S{h.new_severity}</span>
                {h.is_physical_change && <Status tone="warn" shape="diamond">физическое изменение</Status>}
              </div>
              <div className="small" style={{ marginTop: 4 }}>
                {h.previous_condition && <span className="faint">{label.condition(h.previous_condition)} → </span>}
                <Status tone={conditionTone(h.new_condition)}>{label.condition(h.new_condition)}</Status>
              </div>
              <span className="mono faint" style={{ fontSize: 'var(--text-micro)' }}>{label.changeSource(h.change_source)}</span>
            </div>
          </div>
        ))}
        <div className="spec-timeline-item">
          <i className={`spec-dot tone-${confirmed === false ? 'neutral' : 'ok'}`} aria-hidden />
          <div>
            <div className="spec-row" style={{ padding: 0 }}>
              <span className="mono small">решение оператора</span>
            </div>
            <div className="small" style={{ marginTop: 4 }}>
              {confirmed === false ? (
                <Status tone="neutral">REJECTED · предсказание сохранено</Status>
              ) : (
                <Status tone="ok">HUMAN_REVIEW · подтверждено</Status>
              )}
            </div>
            <span className="mono faint" style={{ fontSize: 'var(--text-micro)' }}>append-only: исходные предсказания не затираются</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export default function Scenario() {
  const headRef = useReveal<HTMLDivElement>();
  const [step, setStep] = useState(0);
  const [decision, setDecision] = useState<boolean | null>(null);

  const obs = useMemo(
    () => demoData.observations.find((o) => o.condition_class === 'missing_cover' && o.asset_id) ?? demoData.observations[0],
    [],
  );
  const asset = demoData.assets.find((a) => a.id === obs.asset_id);
  const dedupDistance = ((obs.dedup_explanation ?? {}) as Record<string, unknown>).distance_m;
  const framePlain = useMemo(() => `data:image/svg+xml;charset=utf-8,${encodeURIComponent(demoFrameSvg(obs, false))}`, [obs]);
  const frameBbox = useMemo(() => `data:image/svg+xml;charset=utf-8,${encodeURIComponent(demoFrameSvg(obs, true))}`, [obs]);

  const steps = [
    { title: 'Кадр с маршрута', text: `Объезд «${demoData.routes[0].name}». Камера служебного автомобиля фиксирует уличную инфраструктуру; GPS-трек привязывает кадр к координатам.` },
    { title: 'Детекция и оценка', text: `Модель обнаруживает ${label.assetType(obs.object_type).toLowerCase()} и классифицирует состояние: ${label.condition(obs.condition_class)}. Уверенность детектора — ${fmtPercent(obs.detector_confidence, 0)}, тяжесть S${obs.severity}.` },
    { title: 'Дедупликация', text: `Система сравнивает обнаружение с реестром: расстояние ${fmtNumber(Number(dedupDistance ?? 0), 1)} м, совпадение типа и состояния. Объект не дублируется — наблюдение привязывается к существующему Asset.` },
    { title: 'Карточка наблюдения', text: 'Формируется наблюдение: исходное предсказание, bbox в пикселях кадра, геопривязка, результат дедупликации. Запись ожидает проверки оператором.' },
    { title: 'Решение оператора', text: 'Оператор сравнивает кадр с предсказанием и принимает решение. Подтверждение обновляет состояние объекта; отклонение сохраняет предсказание, но не применяет его.' },
    { title: 'История состояния', text: 'Изменение фиксируется в истории с источником HUMAN_REVIEW. Между объездами состояние ухудшилось: damaged_cover → missing_cover. Это видно в паспорте объекта.' },
  ];

  const visual = () => {
    switch (step) {
      case 0:
        return <img src={framePlain} alt="Синтетический кадр объезда без разметки" />;
      case 1:
        return <img src={frameBbox} alt="Синтетический кадр с bbox детекции" />;
      case 2:
        return <DedupVisual obs={obs} asset={asset} />;
      case 3:
        return (
          <div style={{ padding: 'var(--sp-6)' }}>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 'var(--sp-4)' }}>
              <Badge>наблюдение · {obs.id.slice(0, 8)}</Badge>
              <Status tone="warn">не проверено</Status>
              <Status tone="ok" shape="square">matched</Status>
            </div>
            <KeyValue
              items={[
                ['Объект', asset?.display_name ?? '—'],
                ['Тип', label.assetType(obs.object_type)],
                ['Состояние (ML)', <Status tone="crit">{label.condition(obs.condition_class)}</Status>],
                ['Тяжесть', <Severity value={obs.severity} />],
                ['Уверенность', <span className="num">{fmtPercent(obs.detector_confidence, 1)}</span>],
                ['Координаты', <span className="mono small">{obs.latitude?.toFixed(5)}, {obs.longitude?.toFixed(5)}</span>],
                ['Время', fmtDateTime(obs.observed_at)],
              ]}
            />
          </div>
        );
      case 4:
        return (
          <div style={{ padding: 'var(--sp-6)' }}>
            <img src={frameBbox} alt="Кадр для проверки" style={{ borderRadius: 5, border: '1px solid var(--line-soft)' }} />
            <div style={{ display: 'flex', gap: 'var(--sp-3)', marginTop: 'var(--sp-5)', flexWrap: 'wrap' }}>
              <Button variant={decision === true ? 'primary' : 'default'} onClick={() => setDecision(true)}>
                <IconCheck className="icon-sm" /> Подтвердить дефект
              </Button>
              <Button variant={decision === false ? 'danger' : 'default'} onClick={() => setDecision(false)}>
                <IconClose className="icon-sm" /> Отклонить
              </Button>
            </div>
            <p className="small muted" style={{ marginTop: 'var(--sp-4)' }} aria-live="polite">
              {decision === null && 'Выберите решение, чтобы увидеть, как оно отразится на истории объекта.'}
              {decision === true && 'Решение CONFIRMED: состояние объекта обновится, дефект подтверждён, запись добавлена в историю.'}
              {decision === false && 'Решение REJECTED: предсказание сохранено в журнале, но состояние объекта не изменяется.'}
            </p>
          </div>
        );
      default:
        return <HistoryVisual assetId={obs.asset_id} confirmed={decision} />;
    }
  };

  return (
    <section className="sc-section scenario" id="scenario" aria-label="Сценарий: от обнаружения до решения">
      <div className="sc-section-head reveal" ref={headRef}>
        <p className="sc-eyebrow">Intelligence in Action</p>
        <h2>Один дефект — весь путь решения</h2>
        <p>
          Конкретный сценарий на синтетических данных: обнаружение → сопоставление → наблюдение →
          проверка → история. Пройдите шаги вручную.
        </p>
        <div style={{ marginTop: 'var(--sp-4)' }}>
          <Badge demo>
            <span style={{ whiteSpace: 'normal', lineHeight: 1.5 }}>ДЕМОНСТРАЦИОННЫЙ СЦЕНАРИЙ · СИНТЕТИЧЕСКИЕ ДАННЫЕ</span>
          </Badge>
        </div>
      </div>

      <div className="scenario-grid">
        <nav className="scenario-rail" aria-label="Шаги сценария">
          {steps.map((s, i) => (
            <button key={s.title} className="scenario-step-btn" aria-current={step === i ? 'step' : undefined} onClick={() => setStep(i)}>
              <span className="step-n">{String(i + 1).padStart(2, '0')}</span>
              <span className="step-t">{s.title}</span>
            </button>
          ))}
        </nav>

        <div className="scenario-stage">
          <div className="scenario-visual" key={step}>
            {visual()}
          </div>
          <div className="scenario-text">
            <h3>{steps[step].title}</h3>
            <p>{steps[step].text}</p>
          </div>
          <div className="scenario-controls">
            <Button disabled={step === 0} onClick={() => setStep((s) => Math.max(0, s - 1))}>
              <IconChevronLeft className="icon-sm" /> Назад
            </Button>
            <Button variant="primary" disabled={step === steps.length - 1} onClick={() => setStep((s) => Math.min(steps.length - 1, s + 1))}>
              Далее <IconArrowRight className="icon-sm" />
            </Button>
            <span className="mono faint small">
              шаг {step + 1}/{steps.length}
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}