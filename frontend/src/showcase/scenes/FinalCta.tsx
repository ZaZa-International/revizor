import { Link, useNavigate } from 'react-router-dom';
import { useDataSource } from '../../data/source';
import { useAuth } from '../../api/auth';
import { IconArrowRight } from '../../components/icons';
import { useReveal } from '../motion';

export default function FinalCta() {
  const ref = useReveal<HTMLDivElement>(0.25);
  const { setMode } = useDataSource();
  const { session } = useAuth();
  const navigate = useNavigate();

  const openDemo = () => {
    setMode('demo');
    navigate('/app');
  };

  return (
    <section className="final" aria-label="Переход в платформу">
      <div className="final-media">
        <img
          src="/assets/img/skyline-1280.webp"
          srcSet="/assets/img/skyline-1280.webp 1280w, /assets/img/skyline-1920.webp 1920w"
          sizes="100vw"
          alt="Панорама городской застройки"
          loading="lazy"
          style={{ background: 'url(/assets/img/skyline-lqip.webp) center/cover' }}
        />
      </div>
      <div className="final-shade" />
      <div className="final-content reveal" ref={ref}>
        <p className="sc-eyebrow">Revizor Command Center</p>
        <h2 className="final-title" style={{ marginTop: 'var(--sp-4)' }}>
          Управляйте состоянием инфраструктуры
        </h2>
        <p className="final-sub">
          Реестр объектов, карта сети, очередь проверки, задачи обработки и аналитика покрытия —
          в единой рабочей среде. {session ? 'Вы авторизованы: данные API доступны.' : 'Войдите или откройте демо-режим без сервера.'}
        </p>
        <div className="final-cta">
          <Link className="btn btn-primary btn-lg" to="/app">
            Открыть Revizor Command Center <IconArrowRight className="icon-sm" />
          </Link>
          {!session && (
            <button className="btn btn-lg" onClick={openDemo}>
              Демо-режим без сервера
            </button>
          )}
          <a className="link small" href="/docs" target="_blank" rel="noreferrer">
            Документация API (Developer Portal)
          </a>
        </div>
      </div>
    </section>
  );
}