import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import Hero from './scenes/Hero';
import InvisibleNetwork from './scenes/InvisibleNetwork';
import Pipeline from './scenes/Pipeline';
import DigitalTwin from './scenes/DigitalTwin';
import Scenario from './scenes/Scenario';
import PlatformPreview from './scenes/PlatformPreview';
import FinalCta from './scenes/FinalCta';
import { useShowcaseData } from './useShowcaseData';
import { IconArrowRight } from '../components/icons';

export default function ShowcasePage() {
  const [scrolled, setScrolled] = useState(false);
  const { live, overview } = useShowcaseData();

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 40);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const stats = {
    assets: overview?.assets_total ?? (live ? 0 : 18),
    observations: overview?.observations_total ?? (live ? 0 : 34),
    defects: overview?.defects_total ?? (live ? 0 : 12),
    demo: !live,
  };

  return (
    <div className="showcase">
      <a className="skip-link" href="#pipeline">
        К содержанию
      </a>
      <header className={`sc-nav${scrolled ? ' scrolled' : ''}`}>
        <a className="sc-brand" href="/" aria-label="Revizor — главная">
          <img src="/favicon.svg" alt="" width={30} height={30} />
          <span className="sc-brand-name">Revizor</span>
        </a>
        <nav className="sc-nav-links" aria-label="Разделы презентации">
          <a href="#network">Сеть</a>
          <a href="#pipeline">Pipeline</a>
          <a href="#twin">Карта</a>
          <a href="#scenario">Сценарий</a>
          <a href="#platform">Платформа</a>
        </nav>
        <div className="sc-nav-cta">
          <Link className="btn btn-primary btn-sm" to="/app">
            Открыть платформу <IconArrowRight className="icon-sm" />
          </Link>
        </div>
      </header>

      <main>
        <Hero live={live} />
        <div id="network">
          <InvisibleNetwork stats={stats} />
        </div>
        <Pipeline />
        <DigitalTwin />
        <Scenario />
        <PlatformPreview />
        <FinalCta />
      </main>

      <footer className="sc-footer">
        <div className="sc-footer-col">
          <strong style={{ color: 'var(--muted)' }}>REVIZOR · Infrastructure Intelligence</strong>
          <br />
          MVP хакатона. Демо-данные синтетические и маркированы; реальные измерения подключаются
          через API backend. ML-модель — за стабильным контрактом (в MVP mock-провайдер).
        </div>
        <div className="sc-footer-col">
          Фотографии:{' '}
          <a href="https://commons.wikimedia.org/wiki/File:Moscow,_Aerial_view_over_night_Moscow,_Russia.jpg" target="_blank" rel="noreferrer">
            ночная аэросъёмка
          </a>{' '}
          и{' '}
          <a href="https://commons.wikimedia.org/wiki/File:Moscow,_Aerial_view_over_Moscow,_Russia.jpg" target="_blank" rel="noreferrer">
            дневная аэросъёмка
          </a>{' '}
          — Vyacheslav Argenberg,{' '}
          <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">CC BY 4.0</a>;{' '}
          <a href="https://commons.wikimedia.org/wiki/File:Moscow_-_Skyline_-_2026-09_-_p02.jpg" target="_blank" rel="noreferrer">
            панорама
          </a>{' '}
          — CC0. Шрифты: Oswald, IBM Plex Sans, JetBrains Mono (OFL).
        </div>
        <div className="sc-footer-col">
          <Link to="/app">Command Center</Link>
          {' · '}
          <a href="/docs" target="_blank" rel="noreferrer">API docs</a>
          {' · '}
          <a href="https://github.com/ZaZa-International/kaspian-digital-forum" target="_blank" rel="noreferrer">
            референс исполнения
          </a>
          <br />
          Карта: © Esri · HERE · Garmin · FAO · NOAA · USGS.
        </div>
      </footer>
    </div>
  );
}