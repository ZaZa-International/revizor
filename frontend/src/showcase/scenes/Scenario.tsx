import { useMemo, useState } from 'react';
import { demoData } from '../../demo/data';
import { demoFrameSvg } from '../../demo/frames';
import { Badge, Button, KeyValue, Severity, Status } from '../../components/ui';
import { IconArrowRight, IconCheck, IconChevronLeft, IconClose } from '../../components/icons';
import { useReveal } from '../motion';
import { label } from '../../lib/labels';
import { fmtDateTime, fmtPercent } from '../../lib/format';

const ACC = '#75D7CC';
const CRIT = '#E66C61';

function DedupVisual() {
  return (
    <svg viewBox="0 0 800 300" role="img" aria-label="Сопоставление обнаружения с существующим объектом">
      <rect width="800" height="300" fill="#091318" />
      <circle cx="220" cy="150" r="46" fill="none" stroke={ACC} strokeWidth="3" />
      <circle cx="220" cy="150" r="12" fill={ACC} />
      <text x="220" y="230" textAnchor="middle" fontFamily="monospace" fontSize="17" fill="#A0B3B5">DETECTION · 55.7561, 37.6182</text>
      <circle cx="580" cy="150" r="46" fill="none" stroke="#E9EEE9" strokeWidth="3" />
      <circle cx="580" cy="150" r="12" fill="#E9EEE9" />
      <text x="580" y="230" textAnchor="middle" fontFamily="monospace" fontSize="17" fill="#A0B3B5">ASSET · колодец №4202</text>
      <path d="M270 150 H530" stroke={ACC} strokeWidth="2.6" strokeDasharray="8 7" />
      <rect x="330" y="96" width="140" height="34" rx="4" fill="#102129" stroke="#24404A" />
      <text x="400" y="118" textAnchor="middle" fontFamily="monospace" fontSize="16" fill={ACC}>Δ 2.1 м · тип ✓</text>
      <text x="400" y="270" textAnchor="middle" fontFamily="monospace" fontSize="16" fill="#9DBFA8">MATCHED · score 0.91 · объект не дублируется</text>
    </svg>
  );
}

function HistoryVisual({ confirmed }: { confirmed: boolean | null }) {
  return (
    <svg viewBox="0 0 800 300" role="img" aria-label="История состояния объекта">
      <rect width="800" height="300" fill="#091318" />
      <path d="M80 150 H720" stroke="#24404A" strokeWidth="3" />
      <circle cx="140" cy="150" r="13" fill="#9DBFA8" />
      <circle cx="400" cy="150" r="13" fill="#F0A45C" />
      <circle cx="660" cy="150" r="13" fill={confirmed === false ? '#A0B3B5' : CRIT} />
      <text x="140" y="110" textAnchor="middle" fontFamily="monospace" fontSize="15" fill="#A0B3B5">01.11 · ok · S1</text>
      <text x="400" y="110" textAnchor="middle" fontFamily="monospace" fontSize="15" fill="#A0B3B5">10.11 · damaged_cover · S4</text>
      <text x="660" y="110" textAnchor="middle" fontFamily="monospace" fontSize="15" fill="#A0B3B5">15.11 · missing_cover · S5</text>
      <text x="140" y="196" textAnchor="middle" fontFamily="monospace" fontSize="13" fill="#7D959B">ML_PREDICTION</text>
      <text x="400" y="196" textAnchor="middle" fontFamily="monospace" fontSize="13" fill="#7D959B">ML_PREDICTION</text>
      <text x="660" y="196" textAnchor="middle" fontFamily="monospace" fontSize="13" fill="#7D959B">
        {confirmed === false ? 'REJECTED · предсказание сохранено' : 'HUMAN_REVIEW · подтверждено'}
      </text>
      <text x="400" y="262" textAnchor="middle" fontFamily="monospace" fontSize="15" fill={ACC}>
        append-only: исходные предсказания не затираются
      </text>
    </svg>
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
  const framePlain = useMemo(() => `data:image/svg+xml;charset=utf-8,${encodeURIComponent(demoFrameSvg(obs, false))}`, [obs]);
  const frameBbox = useMemo(() => `data:image/svg+xml;charset=utf-8,${encodeURIComponent(demoFrameSvg(obs, true))}`, [obs]);

  const steps = [
    { title: 'Кадр с маршрута', text: `Объезд «${demoData.routes[0].name}». Камера служебного автомобиля фиксирует уличную инфраструктуру; GPS-трек привязывает кадр к координатам.` },
    { title: 'Детекция и оценка', text: `Модель обнаруживает ${label.assetType(obs.object_type).toLowerCase()} и классифицирует состояние: ${label.condition(obs.condition_class)}. Уверенность детектора — ${fmtPercent(obs.detector_confidence, 0)}, тяжесть S${obs.severity}.` },
    { title: 'Дедупликация', text: 'Система сравнивает обнаружение с реестром: расстояние 2.1 м, совпадение типа и состояния. Объект не дублируется — наблюдение привязывается к существующему Asset.' },
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
        return <DedupVisual />;
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
        return <HistoryVisual confirmed={decision} />;
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
          <div className="scenario-visual" key={step} style={{ animation: 'toast-in var(--dur-swap) var(--ease-out)' }}>
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