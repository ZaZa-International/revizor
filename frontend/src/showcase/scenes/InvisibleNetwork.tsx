import { useEffect, useRef, useState } from 'react';
import gsap from 'gsap';
import { ScrollTrigger } from 'gsap/ScrollTrigger';
import NetworkSvg from '../NetworkSvg';
import { prefersReducedMotion } from '../motion';

gsap.registerPlugin(ScrollTrigger);

export interface NetStats {
  assets: number;
  observations: number;
  defects: number;
  demo: boolean;
}

const clamp01 = (v: number) => Math.max(0, Math.min(1, v));

export default function InvisibleNetwork({ stats }: { stats: NetStats }) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [p, setP] = useState(prefersReducedMotion() ? 1 : 0);
  const reduced = prefersReducedMotion();

  useEffect(() => {
    const track = trackRef.current;
    if (!track || reduced) return;
    const ctx = gsap.context(() => {
      ScrollTrigger.create({
        trigger: track,
        start: 'top top',
        end: 'bottom bottom',
        scrub: 0.6,
        onUpdate: (self) => setP(self.progress),
      });
    }, track);
    return () => ctx.revert();
  }, [reduced]);

  const photoOpacity = reduced ? 0.16 : 1 - clamp01((p - 0.12) / 0.42);
  const netProgress = reduced ? 1 : clamp01((p - 0.28) / 0.52);
  const cap1 = reduced ? 0 : 1 - clamp01((p - 0.16) / 0.14);
  const cap2 = reduced ? 0 : clamp01((p - 0.4) / 0.12) * (1 - clamp01((p - 0.72) / 0.1));
  const cap3 = reduced ? 1 : clamp01((p - 0.78) / 0.14);
  const statProgress = reduced ? 1 : clamp01((p - 0.68) / 0.26);
  const legendOpacity = reduced ? 1 : clamp01((p - 0.5) / 0.15);

  return (
    <div className="net-track" ref={trackRef} style={{ height: reduced ? 'auto' : '260vh' }} aria-label="От города к сети">
      <div className="net-stage" style={reduced ? { position: 'relative', height: '100dvh' } : undefined}>
        <div className="net-photo" style={{ opacity: photoOpacity }}>
          <img
            src="/assets/img/aerial-day-1280.webp"
            srcSet="/assets/img/aerial-day-768.webp 768w, /assets/img/aerial-day-1280.webp 1280w, /assets/img/aerial-day-1920.webp 1920w"
            sizes="100vw"
            alt="Дневная аэрофотосъёмка городской застройки"
            loading="lazy"
            style={{ background: 'url(/assets/img/aerial-day-lqip.webp) center/cover' }}
          />
        </div>
        <div className="net-dark" style={{ opacity: reduced ? 0.84 : clamp01((p - 0.12) / 0.42) * 0.94 }} />
        <NetworkSvg className="net-svg" progress={netProgress} />

        <div className="net-legend" style={{ opacity: legendOpacity }}>
          <span><i style={{ borderRadius: '50%', border: '2px solid #75D7CC' }} /> кабельный колодец</span>
          <span><i style={{ border: '2px solid #E9EEE9', borderRadius: 2 }} /> телеком-шкаф</span>
          <span><i style={{ width: 0, height: 0, borderLeft: '6px solid transparent', borderRight: '6px solid transparent', borderBottom: '10px solid #75D7CC' }} /> опора</span>
          <span><i style={{ borderRadius: '50%', border: '2px dashed #E66C61' }} /> дефект</span>
          <span style={{ color: 'var(--faint)' }}>схема сети · не географическая карта</span>
        </div>

        <div className="net-stats" style={{ opacity: statProgress }}>
          <div className="net-stat">
            <div className="net-stat-value">{Math.round(stats.assets * statProgress)}</div>
            <div className="net-stat-label">объектов в реестре</div>
          </div>
          <div className="net-stat">
            <div className="net-stat-value">{Math.round(stats.observations * statProgress)}</div>
            <div className="net-stat-label">наблюдений</div>
          </div>
          <div className="net-stat">
            <div className="net-stat-value">{Math.round(stats.defects * statProgress)}</div>
            <div className="net-stat-label">дефектов выявлено</div>
          </div>
          {stats.demo && <span className="badge badge-demo" style={{ alignSelf: 'flex-end' }}>DEMO-СЦЕНАРИЙ</span>}
        </div>

        <div className="net-caption" style={{ opacity: cap1, visibility: cap1 < 0.02 ? 'hidden' : 'visible' }}>
          <h2>Город — это улицы и здания.</h2>
          <p>
            На поверхности — фасады, дороги и дворы. Инфраструктура связи скрыта под асфальтом,
            в распределительных шкафах и на опорах. Её состояние определяет, работает ли сеть.
          </p>
        </div>
        <div className="net-caption" style={{ opacity: cap2, visibility: cap2 < 0.02 ? 'hidden' : 'visible' }}>
          <h2>Под городом — сеть.</h2>
          <p>
            Кабельные колодцы, опоры, шкафы и линии образуют единую систему.
            Каждый объект имеет состояние, приоритет и историю наблюдений.
          </p>
        </div>
        <div className="net-caption" style={{ opacity: cap3, visibility: cap3 < 0.02 ? 'hidden' : 'visible' }}>
          <h2>Revizor делает сеть видимой.</h2>
          <p>
            Наблюдения с объездов превращаются в реестр объектов, дефекты и приоритеты.
            Решения принимает оператор — система сохраняет каждое основание.
          </p>
        </div>
      </div>
    </div>
  );
}