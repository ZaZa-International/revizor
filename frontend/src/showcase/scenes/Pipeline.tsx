import { useEffect, useRef } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import { useReveal, prefersReducedMotion } from '../motion';

gsap.registerPlugin(ScrollTrigger);

const INK = '#14232B';
const ACC = '#0E6E62';
const MUT = '#4E6268';
const LINE = '#C9CFC4';
const CRIT = '#B4453C';
const WARN = '#B06A2C';

function ArtUpload() {
  return (
    <svg viewBox="0 0 200 120" aria-hidden>
      <rect x="18" y="18" width="96" height="62" rx="3" fill="none" stroke={INK} strokeWidth="2" />
      <path d="M18 62 L52 40 L74 56 L96 36 L114 52" stroke={MUT} strokeWidth="2" fill="none" />
      <circle cx="96" cy="32" r="5" fill={WARN} />
      <path d="M132 50 H168 M156 38 l12 12 -12 12" stroke={ACC} strokeWidth="2.6" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      <rect x="150" y="74" width="34" height="26" rx="3" fill="none" stroke={INK} strokeWidth="2" />
      <path d="M156 87 h22" stroke={MUT} strokeWidth="2" />
    </svg>
  );
}

function ArtQuality() {
  return (
    <svg viewBox="0 0 200 120" aria-hidden>
      <rect x="24" y="22" width="70" height="46" rx="3" fill="none" stroke={INK} strokeWidth="2" />
      <path d="M32 56 L48 42 L60 52 L78 36 L86 46" stroke={MUT} strokeWidth="2" fill="none" />
      <circle cx="116" cy="45" r="13" fill="none" stroke={ACC} strokeWidth="2.4" />
      <path d="M110 45 l4.5 4.5 8-9" stroke={ACC} strokeWidth="2.4" fill="none" strokeLinecap="round" />
      <rect x="24" y="76" width="70" height="26" rx="3" fill="none" stroke={LINE} strokeWidth="2" />
      <path d="M30 82 l58 14 M88 82 l-58 14" stroke={CRIT} strokeWidth="1.6" opacity="0.7" />
      <text x="112" y="94" fontFamily="monospace" fontSize="11" fill={MUT}>blur → reject</text>
    </svg>
  );
}

function ArtDetect() {
  return (
    <svg viewBox="0 0 200 120" aria-hidden>
      <rect x="24" y="16" width="152" height="88" rx="3" fill="none" stroke={INK} strokeWidth="2" />
      <path d="M24 78 L70 58 L110 72 L176 52" stroke={LINE} strokeWidth="2" fill="none" />
      <rect x="66" y="42" width="52" height="44" fill="none" stroke={ACC} strokeWidth="2.6" />
      <rect x="66" y="30" width="86" height="12" fill={ACC} />
      <text x="70" y="39" fontFamily="monospace" fontSize="9" fill="#F2F3EF">telecom_well 0.92</text>
      <ellipse cx="92" cy="72" rx="16" ry="7" fill="none" stroke={MUT} strokeWidth="2" />
    </svg>
  );
}

function ArtDedup() {
  return (
    <svg viewBox="0 0 200 120" aria-hidden>
      <circle cx="62" cy="60" r="17" fill="none" stroke={INK} strokeWidth="2.4" />
      <circle cx="62" cy="60" r="5" fill={INK} />
      <circle cx="138" cy="60" r="17" fill="none" stroke={ACC} strokeWidth="2.4" strokeDasharray="5 4" />
      <circle cx="138" cy="60" r="5" fill={ACC} />
      <path d="M82 60 H118" stroke={MUT} strokeWidth="2" strokeDasharray="4 4" />
      <text x="92" y="44" fontFamily="monospace" fontSize="13" fill={WARN}>?</text>
      <text x="44" y="98" fontFamily="monospace" fontSize="10" fill={MUT}>asset</text>
      <text x="118" y="98" fontFamily="monospace" fontSize="10" fill={MUT}>detection</text>
    </svg>
  );
}

function ArtDefect() {
  return (
    <svg viewBox="0 0 200 120" aria-hidden>
      <ellipse cx="100" cy="66" rx="52" ry="20" fill="none" stroke={INK} strokeWidth="2.4" />
      <ellipse cx="100" cy="62" rx="36" ry="13" fill="none" stroke={MUT} strokeWidth="2" />
      <path d="M78 58 L92 66 L86 74 L104 80" stroke={CRIT} strokeWidth="2.6" fill="none" strokeLinecap="round" />
      <path d="M150 30 L162 52 H138 Z" fill="none" stroke={CRIT} strokeWidth="2.2" strokeLinejoin="round" />
      <path d="M150 38 v7 M150 48 v1.6" stroke={CRIT} strokeWidth="2.2" strokeLinecap="round" />
      <text x="30" y="104" fontFamily="monospace" fontSize="10" fill={MUT}>missing_cover · S5</text>
    </svg>
  );
}

function ArtScore() {
  return (
    <svg viewBox="0 0 200 120" aria-hidden>
      <path d="M40 84 A60 60 0 0 1 160 84" fill="none" stroke={LINE} strokeWidth="8" strokeLinecap="round" />
      <path d="M40 84 A60 60 0 0 1 128 32" fill="none" stroke={ACC} strokeWidth="8" strokeLinecap="round" />
      <path d="M100 84 L126 44" stroke={INK} strokeWidth="3" strokeLinecap="round" />
      <circle cx="100" cy="84" r="6" fill={INK} />
      <text x="76" y="106" fontFamily="monospace" fontSize="11" fill={MUT}>priority 87/100</text>
    </svg>
  );
}

function ArtReview() {
  return (
    <svg viewBox="0 0 200 120" aria-hidden>
      <rect x="24" y="24" width="46" height="30" rx="3" fill="none" stroke={ACC} strokeWidth="2.2" />
      <path d="M38 39 l6 6 12-13" stroke={ACC} strokeWidth="2.4" fill="none" strokeLinecap="round" />
      <rect x="78" y="24" width="46" height="30" rx="3" fill="none" stroke={CRIT} strokeWidth="2.2" />
      <path d="M92 32 l18 14 M110 32 l-18 14" stroke={CRIT} strokeWidth="2.2" strokeLinecap="round" />
      <rect x="132" y="24" width="46" height="30" rx="3" fill="none" stroke={INK} strokeWidth="2.2" />
      <path d="M142 39 h26 M155 32 v14" stroke={INK} strokeWidth="2" strokeLinecap="round" />
      <rect x="24" y="66" width="154" height="28" rx="3" fill="none" stroke={LINE} strokeWidth="2" />
      <path d="M32 80 h96" stroke={MUT} strokeWidth="2" strokeDasharray="3 4" />
      <text x="134" y="84" fontFamily="monospace" fontSize="10" fill={MUT}>comment</text>
    </svg>
  );
}

function ArtHistory() {
  return (
    <svg viewBox="0 0 200 120" aria-hidden>
      <path d="M28 60 H172" stroke={LINE} strokeWidth="2.4" />
      <circle cx="48" cy="60" r="7" fill={ACC} />
      <circle cx="96" cy="60" r="7" fill={WARN} />
      <circle cx="144" cy="60" r="7" fill={CRIT} />
      <text x="34" y="40" fontFamily="monospace" fontSize="9" fill={MUT}>01.11</text>
      <text x="82" y="40" fontFamily="monospace" fontSize="9" fill={MUT}>10.11</text>
      <text x="130" y="40" fontFamily="monospace" fontSize="9" fill={MUT}>15.11</text>
      <text x="30" y="86" fontFamily="monospace" fontSize="9" fill={MUT}>ok</text>
      <text x="76" y="86" fontFamily="monospace" fontSize="9" fill={MUT}>damaged</text>
      <text x="124" y="86" fontFamily="monospace" fontSize="9" fill={MUT}>missing</text>
    </svg>
  );
}

const STEPS = [
  { title: 'Загрузка материалов', text: 'Фото и видео с камер служебных автомобилей поступают в систему. GPS-трек объезда привязывает кадры к маршруту.', Art: ArtUpload },
  { title: 'Контроль качества', text: 'Quality gate отклоняет смазанные и засвеченные кадры. Покадровые ошибки не останавливают обработку задачи.', Art: ArtQuality },
  { title: 'Детекция объектов', text: 'Компьютерное зрение находит колодцы, опоры, шкафы и кабельные линии, определяет состояние и уверенность предсказания.', Art: ArtDetect },
  { title: 'Дедупликация', text: 'Обнаружения сопоставляются с существующими объектами по расстоянию, типу и состоянию. Неоднозначные совпадения не объединяются автоматически.', Art: ArtDedup },
  { title: 'Выявление дефектов', text: 'Повреждённые состояния отображаются в дефекты: отсутствующая крышка, наклон опоры, обрыв кабеля. Тяжесть — по шкале S1–S5.', Art: ArtDefect },
  { title: 'Оценка состояния', text: 'Приоритет объекта рассчитывается по формуле severity × impact × confidence. Факторы сохраняются и доступны в паспорте.', Art: ArtScore },
  { title: 'Проверка оператором', text: 'Оператор подтверждает, отклоняет или корректирует результат. Исходное предсказание ML не затирается — история append-only.', Art: ArtReview },
  { title: 'История состояния', text: 'Каждое изменение фиксируется с источником: ML-предсказание, проверка оператором или ручное редактирование.', Art: ArtHistory },
];

function Step({ index, title, text, Art }: { index: number; title: string; text: string; Art: () => JSX.Element }) {
  const ref = useReveal<HTMLDivElement>(0.3);
  return (
    <div className="pipeline-step reveal" ref={ref}>
      <div className="pipeline-num">{String(index + 1).padStart(2, '0')}</div>
      <div className="pipeline-body">
        <h3>{title}</h3>
        <p>{text}</p>
      </div>
      <div className="pipeline-art"><Art /></div>
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
          ошибки изолированы покадрово, повторный запуск идемпотентен.
        </p>
      </div>
      <div className="pipeline">
        <div className="pipeline-line" />
        <div className="pipeline-line-fill" ref={fillRef} style={{ transform: 'scaleY(0)' }} />
        {STEPS.map((s, i) => (
          <Step key={s.title} index={i} title={s.title} text={s.text} Art={s.Art} />
        ))}
      </div>
    </section>
  );
}