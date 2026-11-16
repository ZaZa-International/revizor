import { useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import gsap from 'gsap';
import NetworkSvg from '../NetworkSvg';
import { prefersReducedMotion } from '../motion';
import { IconArrowRight, IconChevronDown } from '../../components/icons';

export default function Hero({ live }: { live: boolean }) {
  const rootRef = useRef<HTMLElement>(null);
  const mediaRef = useRef<HTMLDivElement>(null);
  const [netProgress, setNetProgress] = useState(prefersReducedMotion() ? 1 : 0);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    if (prefersReducedMotion()) {
      setNetProgress(1);
      return;
    }
    const ctx = gsap.context(() => {
      const tl = gsap.timeline({ defaults: { ease: 'power3.out' } });
      tl.from('.hero-eyebrow', { y: 18, opacity: 0, duration: 0.55 })
        .from('.hero-title .line', { y: 34, opacity: 0, duration: 0.7, stagger: 0.12 }, '-=0.3')
        .from('.hero-sub', { y: 20, opacity: 0, duration: 0.55 }, '-=0.4')
        .from('.hero-cta > *', { y: 16, opacity: 0, duration: 0.45, stagger: 0.08 }, '-=0.35')
        .from('.hero-coords', { opacity: 0, duration: 0.6 }, '-=0.3');
      const net = { v: 0 };
      gsap.to(net, {
        v: 1,
        duration: 2.6,
        delay: 0.5,
        ease: 'power2.inOut',
        onUpdate: () => setNetProgress(net.v),
      });
    }, root);

    let raf = 0;
    const onScroll = () => {
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        const media = mediaRef.current;
        if (!media) return;
        const y = window.scrollY;
        if (y < window.innerHeight * 1.2) {
          media.style.transform = `translateY(${y * 0.16}px)`;
        }
      });
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => {
      ctx.revert();
      window.removeEventListener('scroll', onScroll);
      if (raf) cancelAnimationFrame(raf);
    };
  }, []);

  return (
    <section className="hero" ref={rootRef} aria-label="Revizor — мониторинг городской инфраструктуры">
      <div className="hero-media" ref={mediaRef}>
        <img
          src="/assets/img/hero-night-1920.webp"
          srcSet="/assets/img/hero-night-768.webp 768w, /assets/img/hero-night-1280.webp 1280w, /assets/img/hero-night-1920.webp 1920w, /assets/img/hero-night-2560.webp 2560w"
          sizes="100vw"
          alt="Ночная панорама города с высоты"
          style={{ background: 'url(/assets/img/hero-night-lqip.webp) center/cover' }}
        />
      </div>
      <div className="hero-shade" />
      <div className="hero-net">
        <NetworkSvg progress={netProgress} />
      </div>

      <div className="hero-content">
        <div className="hero-eyebrow">
          <span className="eyebrow">Revizor · Infrastructure Intelligence</span>
        </div>
        <h1 className="hero-title">
          <span className="line" style={{ display: 'block' }}>Городская сеть.</span>
          <span className="line accent" style={{ display: 'block' }}>Под наблюдением.</span>
        </h1>
        <p className="hero-sub">
          Интеллектуальный мониторинг состояния городской телекоммуникационной инфраструктуры:
          компьютерное зрение находит объекты и дефекты на фото и видео объездов, оператор подтверждает
          результат, система ведёт историю состояния каждого объекта.
        </p>
        <div className="hero-cta">
          <Link className="btn btn-primary btn-lg" to="/app">
            Открыть платформу <IconArrowRight className="icon-sm" />
          </Link>
          <a className="btn btn-lg" href="#pipeline">
            Как это работает
          </a>
        </div>
      </div>

      <div className="hero-coords" aria-hidden>
        <div><span className="live-dot" />{live ? 'LIVE API · CONNECTED' : 'DEMO SCENARIO'}</div>
        <div>55.7558 N · 37.6173 E</div>
        <div>MOSCOW · GRID 250 M · WGS84</div>
      </div>

      <div className="hero-scroll" aria-hidden>
        <span>город → сеть</span>
        <IconChevronDown className="chev" />
      </div>
    </section>
  );
}