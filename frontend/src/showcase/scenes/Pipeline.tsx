import { useEffect, useRef, type ReactNode } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { useReveal, prefersReducedMotion } from '../motion';
import { demoData } from '../../demo/data';
import { demoFrameDataUrl } from '../../demo/frames';
import { Badge, Progress, Severity, Status } from '../../components/ui';
import { IconCheck, IconClose } from '../../components/icons';
import { bandTone, conditionTone, defectStatusTone, label } from '../../lib/labels';
import { fmtBytes, fmtCoord, fmtDateTime, fmtNumber, fmtPercent } from '../../lib/format';

gsap.registerPlugin(ScrollTrigger);

/* Визуалы стадий — реальные материалы продукта на демо-данных:
   кадры с bbox, покадровые статусы, координаты дедупликации, факторы
   приоритета, решения оператора, история. Никаких выдуманных значений. */

const upload0 = demoData.uploads[0];
const route0 = demoData.routes[0];
const job0 = demoData.jobs[0];
/* demo-датасет хранит поля шире публичного JobFrameResponse (job_id,
   detections_count) — тот же приём, что в demo/provider.ts */
type DemoFrame = (typeof demoData.frames)[number] & { job_id?: string; detections_count?: number };
const job0Frames = (demoData.frames as DemoFrame[]).filter((f) => f.job_id === job0.id);
const framePassed = job0Frames.find((f) => f.status === 'PROCESSED' && (f.detections_count ?? 0) > 0);
const frameRejected = job0Frames.find((f) => f.status === 'REJECTED');
const frameFailed = job0Frames.find((f) => f.status === 'FAILED');

const detectObs = demoData.observations.find((o) => o.condition_class === 'missing_cover' && o.asset_id) ?? demoData.observations[0];
const matchedObs = demoData.observations.find((o) => o.dedup_result === 'MATCHED' && o.asset_id);
const matchedAsset = matchedObs ? demoData.assets.find((a) => a.id === matchedObs.asset_id) : undefined;
const ambObs = demoData.observations.find((o) => o.dedup_result === 'POSSIBLE_MATCH');
const defect0 = demoData.defects.find((d) => (d.severity ?? 0) >= 4) ?? demoData.defects[0];
const defectObs = defect0 ? [...demoData.observations].reverse().find((o) => o.asset_id === defect0.asset_id) : undefined;
const highAsset = demoData.assets.find((a) => a.priority_band === 'HIGH_PRIORITY' && a.priority_factors) ?? demoData.assets[0];
const worsenedAsset = demoData.assets.find((a) => a.current_condition === 'missing_cover');
const historyEntries = worsenedAsset
  ? demoData.history
      .filter((h) => h.asset_id === worsenedAsset.id)
      .sort((a, b) => (a.detected_at ?? '').localeCompare(b.detected_at ?? ''))
  : [];

const expl = (o: typeof matchedObs): Record<string, unknown> => (o?.dedup_explanation ?? {}) as Record<string, unknown>;

function Specimen({ source, children }: { source: string; children: ReactNode }) {
  return (
    <div className="pipeline-specimen">
      <div className="specimen-head">
        <span className="eyebrow">{source}</span>
        <span className="badge badge-demo">DEMO</span>
      </div>
      <div className="specimen-body">{children}</div>
    </div>
  );
}

function UploadSpec() {
  return (
    <Specimen source="/app/jobs · загрузка">
      <div className="spec-row">
        <span className="mono small">{upload0.storage_key.split('/').pop()}</span>
        <span className="muted small">{fmtBytes(upload0.file_size)} · {upload0.content_type}</span>
      </div>
      <div className="spec-row">
        <span className="small">Маршрут: {route0.name}</span>
        <Status tone="ok">загружено</Status>
      </div>
      <Progress value={1} />
      <p className="faint" style={{ fontSize: 'var(--text-micro)', marginTop: 10 }}>
        Checksum SHA-256 проверен: дубликаты не загружаются повторно. GPS-трек маршрута привязывает кадры к координатам.
      </p>
    </Specimen>
  );
}

function QualitySpec() {
  const rows = [framePassed, frameRejected, frameFailed].filter(Boolean);
  return (
    <Specimen source="/app/jobs/:id · quality gate">
      {rows.map((f) => (
        <div className="spec-row" key={f!.id}>
          <span className="mono small">кадр {String(f!.frame_index).padStart(6, '0')}</span>
          <Status tone={f!.status === 'PROCESSED' ? 'ok' : f!.status === 'REJECTED' ? 'warn' : 'crit'} shape="square">
            {label.frameStatus(f!.status)}
          </Status>
          <span className="muted small">
            {f!.status === 'REJECTED' ? `причина: ${f!.reject_reason}` : f!.status === 'FAILED' ? `ошибка: ${f!.error_code}` : `детекций: ${f!.detections_count}`}
          </span>
        </div>
      ))}
      <p className="faint" style={{ fontSize: 'var(--text-micro)', marginTop: 10 }}>
        Задача {job0.id.slice(0, 8)}: обработано {fmtNumber(job0.processed_frames)} из {fmtNumber(job0.total_frames)} ·
        отклонено {fmtNumber(job0.rejected_frames)} · ошибок {fmtNumber(job0.failed_frames)}. Покадровые ошибки не останавливают задачу.
      </p>
    </Specimen>
  );
}

function DetectSpec() {
  return (
    <Specimen source="/app/observations/:id · детекция">
      <img className="spec-frame" src={demoFrameDataUrl(detectObs, true)} alt="Синтетический кадр объезда с bbox детекции" loading="lazy" />
      <div className="spec-chips">
        <Badge>{label.assetType(detectObs.object_type)}</Badge>
        <Status tone={conditionTone(detectObs.condition_class)}>{label.condition(detectObs.condition_class)}</Status>
        <Severity value={detectObs.severity} />
        <span className="num small">confidence {fmtPercent(detectObs.detector_confidence, 0)}</span>
        <span className="mono faint" style={{ fontSize: 'var(--text-micro)' }}>{detectObs.model_name} {detectObs.model_version}</span>
      </div>
    </Specimen>
  );
}

function DedupSpec() {
  const e = expl(matchedObs);
  const ae = expl(ambObs);
  return (
    <Specimen source="/app/observations · дедупликация">
      <div className="spec-row">
        <span className="eyebrow">detection</span>
        <span className="mono small">{fmtCoord(matchedObs?.longitude, matchedObs?.latitude)}</span>
        <span className="muted small">{label.assetType(matchedObs?.object_type ?? '')}</span>
      </div>
      <div className="spec-row">
        <span className="eyebrow">asset</span>
        <span className="mono small">{fmtCoord(matchedAsset?.longitude, matchedAsset?.latitude)}</span>
        <span className="muted small">{matchedAsset?.display_name}</span>
      </div>
      <div className="spec-row">
        <span className="num small">Δ {fmtNumber(Number(e.distance_m ?? 0), 1)} м</span>
        <span className="small">тип: совпадает</span>
        <span className="num small">score {fmtNumber(Number(matchedObs?.dedup_score ?? 0), 2)}</span>
        <Status tone="ok" shape="square">matched</Status>
      </div>
      <hr className="divider" style={{ margin: '12px 0' }} />
      <div className="spec-row">
        <span className="eyebrow">possible match</span>
        <span className="num small">Δ {fmtNumber(Number(ae.distance_m ?? 0), 0)} м · score {fmtNumber(Number(ambObs?.dedup_score ?? 0), 2)}</span>
        <Status tone="warn" shape="square">не объединяется</Status>
      </div>
      <p className="faint" style={{ fontSize: 'var(--text-micro)', marginTop: 10 }}>
        AMBIGUOUS/POSSIBLE_MATCH никогда не объединяется автоматически — решение принимает оператор.
      </p>
    </Specimen>
  );
}

function DefectSpec() {
  return (
    <Specimen source="/app/defects/:id · дефект">
      <div className="spec-split">
        {defectObs && <img className="spec-frame" src={demoFrameDataUrl(defectObs, true)} alt="Синтетический кадр с дефектом" loading="lazy" />}
        <div>
          <div className="spec-chips" style={{ marginTop: 0 }}>
            <Status tone={defectStatusTone[defect0?.status ?? ''] ?? 'neutral'}>{label.defectStatus(defect0?.status ?? '')}</Status>
            <Severity value={defect0?.severity} />
          </div>
          <p className="cell-main" style={{ marginTop: 10 }}>{label.defectType(defect0?.defect_type ?? '')}</p>
          <p className="muted small" style={{ marginTop: 4 }}>
            наблюдений: {defect0?.observation_count ?? '—'} · первое: {fmtDateTime(defect0?.first_detected_at)}
          </p>
          <p className="faint" style={{ fontSize: 'var(--text-micro)', marginTop: 10 }}>
            Тяжесть S1–S5 — отдельная шкала, не путать с confidence детектора.
          </p>
        </div>
      </div>
    </Specimen>
  );
}

function ConditionSpec() {
  const f = (highAsset?.priority_factors ?? {}) as Record<string, unknown>;
  return (
    <Specimen source="/app/assets/:id · оценка состояния">
      <div className="spec-row">
        <span className="small">тяжесть</span>
        <span className="num small">{f.severity != null ? `${f.severity}/5` : '—'}</span>
        <span className="small">impact</span>
        <span className="num small">{fmtNumber(Number(f.impact_factor ?? 0), 2)}</span>
        <span className="small">confidence</span>
        <span className="num small">{fmtPercent(Number(f.confidence ?? 0), 0)}</span>
      </div>
      <div className="spec-row">
        <span className="small">расчётный приоритет</span>
        <span className="num" style={{ fontSize: 22, fontWeight: 700 }}>{fmtNumber(Number(f.computed_priority ?? highAsset?.current_priority ?? 0), 0)}<span className="muted small"> / 100</span></span>
        <Status tone={bandTone[highAsset?.priority_band ?? ''] ?? 'neutral'}>{label.priorityBand(highAsset?.priority_band)}</Status>
      </div>
      <p className="faint" style={{ fontSize: 'var(--text-micro)', marginTop: 10 }}>
        Факторы сохраняются в паспорте объекта (risk policy v{highAsset?.priority_policy_version ?? '1.0'}); ручное переопределение требует основания.
      </p>
    </Specimen>
  );
}

const DECISIONS = [
  { name: 'Подтвердить', hint: 'предсказание верно', key: '1', icon: <IconCheck className="icon-sm" />, color: 'var(--ok)' },
  { name: 'Отклонить', hint: 'ложное обнаружение', key: '2', icon: <IconClose className="icon-sm" />, color: 'var(--crit)' },
  { name: 'Скорректировать', hint: 'тип / состояние / тяжесть', key: '3', icon: null, color: 'var(--warn)' },
  { name: 'Нужны данные', hint: 'недостаточно контекста', key: '4', icon: null, color: 'var(--muted)' },
];

function ReviewSpec() {
  return (
    <Specimen source="/app/reviews · проверка оператором">
      <div className="spec-split">
        <img className="spec-frame" src={demoFrameDataUrl(detectObs, true)} alt="Кадр для проверки оператором" loading="lazy" />
        <div className="spec-decisions">
          {DECISIONS.map((d) => (
            <div className="spec-decision" key={d.name}>
              <span className="spec-decision-name" style={{ color: d.color }}>
                {d.icon} {d.name} <span className="mono faint">[{d.key}]</span>
              </span>
              <span className="faint" style={{ fontSize: 'var(--text-micro)' }}>{d.hint}</span>
            </div>
          ))}
        </div>
      </div>
      <p className="faint" style={{ fontSize: 'var(--text-micro)', marginTop: 10 }}>
        Решения append-only: исходное предсказание ML не затирается, история review сохраняется полностью.
      </p>
    </Specimen>
  );
}

function HistorySpec() {
  return (
    <Specimen source="/app/assets/:id · история состояния">
      <div className="spec-timeline">
        {historyEntries.map((h) => (
          <div className="spec-timeline-item" key={h.id}>
            <i className={`spec-dot tone-${conditionTone(h.new_condition)}`} aria-hidden />
            <div>
              <div className="spec-row" style={{ padding: 0 }}>
                <span className="mono small">{fmtDateTime(h.detected_at)}</span>
                {h.is_physical_change && <Status tone="warn" shape="diamond">физическое изменение</Status>}
              </div>
              <div className="small" style={{ marginTop: 4 }}>
                {h.previous_condition && <span className="faint">{label.condition(h.previous_condition)} → </span>}
                <Status tone={conditionTone(h.new_condition)}>{label.condition(h.new_condition)}</Status>
                <span className="muted"> · S{h.new_severity}</span>
              </div>
              <span className="mono faint" style={{ fontSize: 'var(--text-micro)' }}>{label.changeSource(h.change_source)}</span>
            </div>
          </div>
        ))}
      </div>
      <p className="faint" style={{ fontSize: 'var(--text-micro)', marginTop: 10 }}>
        {worsenedAsset?.display_name}: между объездами состояние ухудшилось. Подтверждение оператором добавляется в историю отдельной записью HUMAN_REVIEW.
      </p>
    </Specimen>
  );
}

const STEPS = [
  { title: 'Загрузка материалов', text: 'Фото и видео с камер служебных автомобилей поступают в систему. GPS-трек объезда привязывает кадры к маршруту.', Spec: UploadSpec },
  { title: 'Контроль качества', text: 'Quality gate отклоняет смазанные и засвеченные кадры. Покадровые ошибки не останавливают обработку задачи.', Spec: QualitySpec },
  { title: 'Детекция объектов', text: 'Компьютерное зрение находит колодцы, опоры, шкафы и кабельные линии, определяет состояние и уверенность предсказания.', Spec: DetectSpec },
  { title: 'Дедупликация', text: 'Обнаружения сопоставляются с существующими объектами по расстоянию, типу и состоянию. Неоднозначные совпадения не объединяются автоматически.', Spec: DedupSpec },
  { title: 'Выявление дефектов', text: 'Повреждённые состояния отображаются в дефекты: отсутствующая крышка, наклон опоры, обрыв кабеля. Тяжесть — по шкале S1–S5.', Spec: DefectSpec },
  { title: 'Оценка состояния', text: 'Приоритет объекта рассчитывается по факторам тяжести, влияния и уверенности. Факторы сохраняются и доступны в паспорте.', Spec: ConditionSpec },
  { title: 'Проверка оператором', text: 'Оператор подтверждает, отклоняет или корректирует результат. Исходное предсказание ML не затирается — история append-only.', Spec: ReviewSpec },
  { title: 'История состояния', text: 'Каждое изменение фиксируется с источником: ML-предсказание, проверка оператором или ручное редактирование.', Spec: HistorySpec },
];

function Step({ index, title, text, Spec }: { index: number; title: string; text: string; Spec: () => ReactNode }) {
  const ref = useReveal<HTMLDivElement>(0.2);
  return (
    <div className="pipeline-step reveal" ref={ref}>
      <div className="pipeline-num">{String(index + 1).padStart(2, '0')}</div>
      <div className="pipeline-body">
        <h3>{title}</h3>
        <p>{text}</p>
        <Spec />
      </div>
    </div>
  );
}

export default function Pipeline() {
  const sectionRef = useRef<HTMLElement>(null);
  const fillRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const section = sectionRef.current;
    const fill = fillRef.current;
    if (!section || !fill || prefersReducedMotion()) {
      fill?.style.setProperty('transform', 'scaleY(1)');
      return;
    }
    const ctx = gsap.context(() => {
      gsap.fromTo(fill, { scaleY: 0 }, {
        scaleY: 1,
        ease: 'none',
        scrollTrigger: { trigger: section, start: 'top 70%', end: 'bottom 65%', scrub: 0.4 },
      });
    }, section);
    return () => ctx.revert();
  }, []);

  return (
    <section className="sc-section pipeline-section" id="pipeline" ref={sectionRef} aria-label="Как работает Revizor">
      <div className="sc-section-head">
        <p className="sc-eyebrow">Pipeline · 8 стадий</p>
        <h2>От кадра объезда — к проверенному состоянию объекта</h2>
        <p>
          Реальный конвейер обработки backend: каждая стадия имеет отдельную ответственность,
          ошибки изолированы покадрово, повторный запуск идемпотентен. Ниже — материалы продукта
          на демонстрационных данных.
        </p>
      </div>
      <div className="pipeline">
        <div className="pipeline-line" />
        <div className="pipeline-line-fill" ref={fillRef} style={{ transform: 'scaleY(0)' }} />
        {STEPS.map((s, i) => (
          <Step key={s.title} index={i} title={s.title} text={s.text} Spec={s.Spec} />
        ))}
      </div>
    </section>
  );
}