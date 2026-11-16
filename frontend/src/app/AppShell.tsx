import { useMemo } from 'react';
import { NavLink, Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../api/auth';
import { usePermissions } from '../lib/permissions';
import { useDataSource } from '../data/source';
import { useObservations } from '../data/hooks';
import { DemoBanner, Badge, Button } from '../components/ui';
import {
  IconAnalytics,
  IconAsset,
  IconDefect,
  IconExport,
  IconJob,
  IconLogout,
  IconMap,
  IconObservation,
  IconOverview,
  IconReview,
  IconRoute,
} from '../components/icons';
import { label } from '../lib/labels';

const NAV = [
  { to: '/app', end: true, label: 'Обзор', icon: IconOverview },
  { to: '/app/map', label: 'Карта', icon: IconMap },
  { to: '/app/assets', label: 'Объекты', icon: IconAsset },
  { to: '/app/observations', label: 'Наблюдения', icon: IconObservation },
  { to: '/app/defects', label: 'Дефекты', icon: IconDefect },
  { to: '/app/reviews', label: 'Проверка', icon: IconReview },
  { to: '/app/jobs', label: 'Задачи', icon: IconJob },
  { to: '/app/routes', label: 'Маршруты', icon: IconRoute },
  { to: '/app/analytics', label: 'Аналитика', icon: IconAnalytics },
  { to: '/app/exports', label: 'Выгрузки', icon: IconExport },
];

const TITLES: Record<string, string> = {
  '/app': 'Обзор инфраструктуры',
  '/app/map': 'Карта сети',
  '/app/assets': 'Реестр объектов',
  '/app/observations': 'Наблюдения',
  '/app/defects': 'Дефекты',
  '/app/reviews': 'Проверка оператором',
  '/app/jobs': 'Задачи обработки',
  '/app/routes': 'Маршруты обследования',
  '/app/analytics': 'Аналитика',
  '/app/exports': 'Выгрузки',
};

export default function AppShell() {
  const { session, logout } = useAuth();
  const { canMutate } = usePermissions();
  const { setMode, isDemo } = useDataSource();
  const location = useLocation();
  const navigate = useNavigate();

  const queue = useObservations({ review_status: 'UNREVIEWED', page_size: 1 });
  const queueCount = queue.data?.total ?? 0;

  const title = useMemo(() => {
    const path = location.pathname;
    if (TITLES[path]) return TITLES[path];
    const seg = path.split('/').filter(Boolean);
    if (seg[1] === 'assets') return 'Паспорт объекта';
    if (seg[1] === 'observations') return 'Наблюдение';
    if (seg[1] === 'defects') return 'Дефект';
    if (seg[1] === 'jobs') return 'Задача обработки';
    if (seg[1] === 'routes') return 'Маршрут';
    return 'Revizor';
  }, [location.pathname]);

  if (!isDemo && !session) {
    return <Navigate to="/login" state={{ next: location.pathname + location.search }} replace />;
  }

  const switchMode = () => {
    if (isDemo) {
      setMode('live');
      if (!session) navigate('/login', { state: { next: location.pathname } });
    } else {
      setMode('demo');
    }
  };

  const userBlock = (
    <div className="shell-user">
      <span className="user-name">{isDemo ? 'demo-operator' : session?.user.username}</span>
      <Badge>{label.role(isDemo ? 'OPERATOR' : session?.user.role)}</Badge>
    </div>
  );

  return (
    <div className="shell">
      <a className="skip-link" href="#app-main">
        К содержимому
      </a>
      <aside className="shell-rail" aria-label="Разделы платформы">
        <a className="shell-brand" href="/" aria-label="Revizor — на главную">
          <img src="/favicon.svg" alt="" width={34} height={34} />
          <span>
            <span className="shell-brand-name">Revizor</span>
            <span className="shell-brand-sub" style={{ display: 'block' }}>
              Infrastructure Intelligence
            </span>
          </span>
        </a>
        <nav className="shell-nav" aria-label="Платформа">
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end}>
              <item.icon />
              {item.label}
              {item.to === '/app/reviews' && queueCount > 0 && (
                <span className="nav-count" aria-label={`${queueCount} в очереди`}>
                  {queueCount}
                </span>
              )}
            </NavLink>
          ))}
        </nav>
        <div className="shell-rail-foot">
          {userBlock}
          <Button size="sm" variant="ghost" onClick={switchMode} block>
            {isDemo ? 'Подключиться к серверу' : 'Демо-режим'}
          </Button>
          {!isDemo && (
            <Button size="sm" variant="ghost" onClick={() => void logout().then(() => navigate('/login'))} block>
              <IconLogout className="icon-sm" /> Выйти
            </Button>
          )}
          <a className="btn btn-sm btn-ghost" href="/" style={{ justifyContent: 'center' }}>
            ← Презентация продукта
          </a>
        </div>
      </aside>

      <div className="shell-mobile-bar">
        <div className="shell-mobile-head">
          <a className="shell-brand" href="/" style={{ padding: 0 }} aria-label="Revizor — на главную">
            <img src="/favicon.svg" alt="" width={28} height={28} />
            <span className="shell-brand-name" style={{ fontSize: 16 }}>
              Revizor
            </span>
          </a>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {isDemo && <Badge demo>DEMO</Badge>}
            <Button size="sm" variant="ghost" onClick={switchMode}>
              {isDemo ? 'К серверу' : 'Демо'}
            </Button>
            {!isDemo && (
              <Button size="sm" variant="ghost" aria-label="Выйти" onClick={() => void logout().then(() => navigate('/login'))}>
                <IconLogout className="icon-sm" />
              </Button>
            )}
          </div>
        </div>
        <nav className="shell-mobile-nav" aria-label="Платформа">
          {NAV.map((item) => (
            <NavLink key={item.to} to={item.to} end={item.end}>
              {item.label}
              {item.to === '/app/reviews' && queueCount > 0 && <span className="num">· {queueCount}</span>}
            </NavLink>
          ))}
        </nav>
      </div>

      <div className="shell-main">
        {isDemo && <DemoBanner />}
        <header className="shell-topbar">
          <div className="shell-topbar-left">
            <h1 className="shell-topbar-title">{title}</h1>
            {!canMutate && !isDemo && <Badge>только чтение</Badge>}
          </div>
          <div className="shell-topbar-actions">
            <span className="eyebrow" aria-hidden>
              {isDemo ? 'DEMO DATA' : 'LIVE API'}
            </span>
          </div>
        </header>
        <main className="shell-content" id="app-main">
          <Outlet />
        </main>
      </div>
    </div>
  );
}